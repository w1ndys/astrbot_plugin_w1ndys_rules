# 业务层：本地二维码检出。三级解码器懒加载（微信检测器、zxing-cpp、QReader），
# 每层缺库或失败互不影响，当未检出，不误禁。
# 热路径固定按微信、zxing、QReader 的顺序跑，前一级检出就不跑后面的级，
# 常见码不用等 QReader 的检测模型。
# 检出即违禁，不看载荷。测试可传入 decoder。
# 诊断结果只给测试页和日志用：引擎总状态、三个分层状态、命中层、检出数量和截断载荷。
# 热路径仍只看布尔，诊断不会为了报状态提前加载没走到的后级。

import base64

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    ENGINE_INIT_FAILED,
    ENGINE_MISSING,
    ENGINE_READY,
)

# 第一级：微信检测器实例。没构造成功时留 None。
_wechat = None
# 第二级：zxing-cpp 模块。导入成功这一层就算就绪，它没有单独的权重对象。
_zxing = None
# 第三级：QReader 实例。没构造成功时留 None。
_qreader = None
# 三层各自的加载状态，取值来自 ENGINE_*；空字符串表示这一层本进程还没试过，
# 不能按 missing 报，否则页面会把「没走到这一级」看成「没装库」。
_wechat_state = ""
_zxing_state = ""
_qreader_state = ""
# 引擎总状态不是 ready 时的 warning 只记一次，避免每张图刷同一条日志。
_engine_warned = False
# 诊断返回的载荷每条截断 120 字，页面不展示整段二维码内容
_PAYLOAD_MAX_LEN = 120
# 载荷最多留 3 条，多了对定位漏检没帮助
_PAYLOAD_MAX_ITEMS = 3

# 第二级 zxing 的格式白名单：只认二维码家族。一维商品码不传入也不采纳，
# 否则普通商品照片会被判成二维码违禁。
_ZXING_FORMAT_NAMES = (
    "QRCode",
    "MicroQRCode",
    "RMQRCode",
    "Aztec",
    "DataMatrix",
    "PDF417",
)

# 诊断里的命中层取值，页面按这三个字符串显示层名字；未检出时留空串。
_LAYER_WECHAT = "wechat"
_LAYER_ZXING = "zxing"
_LAYER_QREADER = "qreader"


def qr_found_in_bytes(data: bytes, decoder=None) -> bool:
    """这组字节里有没有二维码。decoder 命中就 True。"""
    return qr_read_bytes(data, decoder)[0]


def qr_read_bytes(data: bytes, decoder=None) -> tuple:
    """返回是否检出，以及截断后的解析文本。有框没文本时仍检出，文本列表为空。"""
    # 空图解不了，三级都不加载
    if not data:
        return False, []
    # 测试注入，不打真实三级引擎
    if decoder is not None:
        try:
            return _decoder_read(decoder(data))
        except Exception:  # noqa: BLE001 - 注入解码失败当未检出
            return False, []
    image = _bgr_from_bytes(data)
    # 解不出 BGR 就不是图片，三级都不调用
    if image is None:
        return False, []
    return _read_from_image(image)


def qr_read_b64(raw: str, decoder=None) -> tuple:
    """base64 图的检出和解析文本。前缀已在采集时剥掉。"""
    text = (raw or "").strip()
    # 空串解不出图
    if not text:
        return False, []
    pad = (-len(text)) % 4
    # 协议端常省略末尾 =
    if pad:
        text = text + ("=" * pad)
    try:
        data = base64.b64decode(text, validate=False)
    except Exception:  # noqa: BLE001 - 坏 base64 当未检出，继续转写
        return False, []
    return qr_read_bytes(data, decoder)


def _decoder_read(result: object) -> tuple:
    """替身返回值收成检出和文本。True 表示有码但没有解析内容。"""
    payloads = _payload_list(_decoder_texts(result))
    # 布尔 True 或框列表仍然算检出，文本另收
    return bool(result), payloads


def _decoder_texts(result: object) -> list:
    """从替身返回里抽出文本。布尔和框对象不是解析内容。"""
    if isinstance(result, (str, bytes)):
        return [result]
    if isinstance(result, (list, tuple)):
        return [item for item in result if isinstance(item, str)]
    return []


def _read_from_image(image) -> tuple:
    """走一遍三级诊断，带出命中层的截断文本。未检出时按引擎状态记一次 warning。"""
    diag = _diagnose_three_layers(image)
    # 三级都没检出时，引擎不可用要留一条痕迹，和原来的热路径一致
    if not diag["found"]:
        _warn_engine_once()
    return bool(diag["found"]), list(diag["payloads"])



def qr_found_in_b64(raw: str, decoder=None) -> bool:
    """base64 图有没有二维码。前缀已在采集时剥掉。"""
    text = (raw or "").strip()
    # 空串解不出图
    if not text:
        return False
    pad = (-len(text)) % 4
    # 协议端常省略末尾 =
    if pad:
        text = text + ("=" * pad)
    try:
        data = base64.b64decode(text, validate=False)
    except Exception:  # noqa: BLE001 - 坏 base64 当未检出，继续转写
        return False
    return qr_found_in_bytes(data, decoder)



def _three_layer_hit(image) -> bool:
    """固定三级顺序：微信检测器、zxing、QReader。前一级检出就不跑后面的级。"""
    # 微信层命中就不用付后两级的时间
    if _wechat_layer_hit(image):
        return True
    # zxing 命中就不用构造 QReader 模型
    if _zxing_layer_hit(image):
        return True
    # 前两级都没解出来，最后才用 QReader 兜住「有框没文本」
    if _qreader_layer_hit(image):
        return True
    # 三级都未检出，引擎总状态不是 ready 时记一次 warning，免得漏检没痕迹
    _warn_engine_once()
    return False


def _wechat_layer_hit(image) -> bool:
    """第一级微信检测器：已构造才跑，异常当未检出并继续后级。"""
    detector = _load_wechat()
    # 这一层缺 contrib 或模型构造失败时跳过，交给后两级兜底
    if detector is None:
        return False
    try:
        return _wechat_hit(detector, image)
    except Exception:  # noqa: BLE001 - 检测器异常不处置消息，继续后级
        return False


def _wechat_texts(detector: object, image) -> list:
    """调一次 detectAndDecode，取文本序列。定位点没有对应文本时这里是空串。"""
    return list(detector.detectAndDecode(image)[0] or [])


def _wechat_hit(detector: object, image) -> bool:
    """至少一条去空白后非空的文本才算检出，只有定位点不算。"""
    # 空文本表示有定位点但没解出内容，不算检出，交给后级兜底
    return _nonblank_text_count(_wechat_texts(detector, image)) > 0


def _zxing_layer_hit(image) -> bool:
    """第二级 zxing-cpp：一次普通读取，异常当未检出并继续后级。"""
    module = _load_zxing()
    # 这一层没导入成功时跳过，交给 QReader 兜底
    if module is None:
        return False
    try:
        return _zxing_hit(module, image)
    except Exception:  # noqa: BLE001 - 解码异常不处置消息，继续后级
        return False


def _zxing_texts(module: object, image) -> list:
    """read_barcodes 一次调用，只留白名单格式且文本非空的结果文本。"""
    formats, allowed = _zxing_format_values(module)
    # 绑定没有格式枚举时不传 formats，返回值仍按白名单过滤，一维码照样不采纳
    if formats is None:
        results = module.read_barcodes(image)
    # 有白名单就只让库认这几种，普通照片上的一维码不会被读出来
    else:
        results = module.read_barcodes(image, formats=formats)
    texts = []
    for item in results or []:
        # 格式不在白名单（EAN、Code 128 这类一维码）或没有文本都不采纳
        if _zxing_item_hit(item, allowed):
            texts.append(getattr(item, "text", ""))
    return texts


def _zxing_hit(module: object, image) -> bool:
    """read_barcodes 一次调用，只采纳白名单格式且文本非空的结果。"""
    return bool(_zxing_texts(module, image))


def _zxing_format_values(module: object) -> tuple:
    """拼 zxing 的格式白名单，绑定里缺哪个枚举就跳过哪个，不整层失败。"""
    enums = getattr(module, "BarcodeFormat", None)
    # 绑定连格式枚举都没有，调用方只能不传 formats，再靠返回值过滤
    if enums is None:
        return None, ()
    combined = None
    allowed = []
    for name in _ZXING_FORMAT_NAMES:
        item = getattr(enums, name, None)
        # 当前绑定缺这个枚举，跳过它，其余枚举继续拼
        if item is None:
            continue
        allowed.append(item)
        combined = item if combined is None else combined | item
    return combined, tuple(allowed)


def _zxing_item_hit(item: object, allowed: tuple) -> bool:
    """结果项格式在白名单内、且文本去空白后非空才算检出。"""
    # 一维商品码不管库默认认不认都不采纳，免得普通图片被判违禁
    if getattr(item, "format", None) not in allowed:
        return False
    return bool(str(getattr(item, "text", "") or "").strip())


def _qreader_layer_hit(image) -> bool:
    """第三级 QReader：有检测框或非空文本都算检出，库缺失或异常当未检出。"""
    reader = _load_qreader()
    # 这一层没起来就跳过，总状态由外面的 warning 统一记一次
    if reader is None:
        return False
    try:
        return _reader_hit(reader, _bgr_to_rgb(image))
    except Exception:  # noqa: BLE001 - 解码超时或模型异常不能误禁
        return False


def _bgr_from_bytes(data: bytes):
    """图片字节收成 BGR 数组，前两级共用这一份。解不出来返回 None。"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        # 没装 OpenCV 或 numpy 就解不了图，三级都跑不了
        return None
    try:
        buffer = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001 - 坏图当未检出，不能误禁
        return None


def _bgr_to_rgb(image):
    """QReader 要 RGB；BGR 反通道即可，只在走到第三级时才转这一次。"""
    # 拷贝成连续内存，免得后级拿到负步长的视图
    return image[:, :, ::-1].copy()


def _load_wechat():
    """懒加载第一级微信检测器。缺 cv2.wechat_qrcode 当 missing，构造失败当 init_failed。"""
    global _wechat, _wechat_state
    # 这一层试过了就复用上次结论，状态的空串才是「还没试过」
    if _wechat_state:
        return _wechat
    try:
        from cv2 import wechat_qrcode
    except ImportError:
        # 装的是不带 contrib 的 OpenCV，缺这个子模块，这一层用不了
        _wechat_state = ENGINE_MISSING
        return None
    try:
        # 无参构造用 contrib 自带模型，容器里 5.0.0 不需要传模型路径
        _wechat = wechat_qrcode.WeChatQRCode()
    except Exception:  # noqa: BLE001 - 模型构造失败只代表这一层不可用，别的层还要试
        _wechat_state = ENGINE_INIT_FAILED
        return None
    _wechat_state = ENGINE_READY
    return _wechat


def _load_zxing():
    """懒加载第二级 zxing-cpp。导入成功这一层就算就绪，导入失败当 missing。"""
    global _zxing, _zxing_state
    # 这一层试过了就复用上次结论
    if _zxing_state:
        return _zxing
    try:
        import zxingcpp
    except ImportError:
        _zxing_state = ENGINE_MISSING
        return None
    _zxing = zxingcpp
    _zxing_state = ENGINE_READY
    return _zxing


def _load_qreader():
    """懒加载第三级 QReader。导入失败当 missing，构造失败当 init_failed，都只试一次。"""
    global _qreader, _qreader_state
    # 这一层试过了就复用上次结论，不再重复导入和构造
    if _qreader_state:
        return _qreader
    try:
        from qreader import QReader
    except ImportError:
        _qreader_state = ENGINE_MISSING
        return None
    try:
        _qreader = QReader()
    except Exception:  # noqa: BLE001 - 权重加载失败只代表这一层不可用，别的层还要试
        _qreader_state = ENGINE_INIT_FAILED
        return None
    _qreader_state = ENGINE_READY
    return _qreader


def _reader_hit(reader: object, image: object) -> bool:
    """有 detect 就看框；否则看 decode 出的非空载荷。"""
    detect = getattr(reader, "detect", None)
    # detect 只回答有没有码，不看内容
    if callable(detect):
        boxes = detect(image=image)
        return _has_items(boxes)
    decode = getattr(reader, "detect_and_decode", None)
    # 老接口只返回文本
    if not callable(decode):
        return False
    texts = decode(image=image)
    # 一个非空载荷就够
    for item in texts or []:
        # 空串不是码
        if item:
            return True
    return False


def _has_items(value: object) -> bool:
    """列表、元组、数组有元素才算检出。"""
    # 解码器没返回
    if value is None:
        return False
    try:
        return len(value) > 0
    except TypeError:
        # 单个框对象也算检出
        return bool(value)


def _reader_texts(reader: object, image: object) -> list:
    """QReader 的文本序列。没有 detect_and_decode 就是空列表。"""
    decode = getattr(reader, "detect_and_decode", None)
    # 老接口连文本方法都没有，只有框能算检出
    if not callable(decode):
        return []
    return _text_items(decode(image=image))


def _qreader_counts(reader: object, image: object) -> tuple:
    """QReader 的框数和载荷：有 detect 就数框，没有 detect 才按非空文本条数数。"""
    detect = getattr(reader, "detect", None)
    # detect 只回答有没有码，数量看框；载荷仍取文本，方便页面看兜底内容
    if callable(detect):
        boxes = detect(image=image)
        box_count = _count_items(boxes) if boxes is not None else 0
        return box_count, _qreader_payloads(reader, image, box_count)
    # 老接口没有 detect，只能按解出的非空文本条数报数量
    texts = _reader_texts(reader, image)
    return _nonblank_text_count(texts), _payload_list(texts)


def _qreader_payloads(reader: object, image: object, box_count: int) -> list:
    """取 QReader 文本。有框时解码失败仍保留框，不当成这一层没检出。"""
    try:
        return _payload_list(_reader_texts(reader, image))
    except Exception:  # noqa: BLE001 - 文本解码失败不能把已经数到的框抹掉
        # 框已经说明有码，文本失败只是页面看不到载荷
        if box_count > 0:
            return []
        raise


def qr_engine_state() -> str:
    """当前二维码引擎状态。会把还没试过的层补试一遍，诊断字段和日志都用它。"""
    # 每层的结果在本进程复用，这里只是补跑还没试过的层
    _load_wechat()
    _load_zxing()
    _load_qreader()
    return _total_state(_tried_states())


def _tried_states() -> list:
    """已经试过的层状态。没试过的层留空串，页面才不会把「没走到」当成「没装库」。"""
    return [state for state in (_wechat_state, _zxing_state, _qreader_state) if state]


def _total_state(states: list) -> str:
    """算引擎总状态：有 ready 就 ready，否则有 init_failed 就 init_failed，否则 missing。"""
    # 任一层能用就算引擎可用，热路径据此继续解码
    if ENGINE_READY in states:
        return ENGINE_READY
    # 有库能导入但都构造失败，问题在模型而不在依赖
    if ENGINE_INIT_FAILED in states:
        return ENGINE_INIT_FAILED
    return ENGINE_MISSING


def _tried_engine_state() -> str:
    """按已经试过的层算总状态；一层都没试过时留空串，不报 missing。"""
    states = _tried_states()
    # 一层都没试过就没有总状态可言，空串让页面走「本次未加载」分支，
    # 不然「没走到」会被读成「没装库」
    if not states:
        return ""
    return _total_state(states)


def qr_diagnose_bytes(data: bytes, decoder=None) -> dict:
    """测试页用的诊断：总状态、三个分层状态、命中层、检出数量和截断载荷。热路径不用它。"""
    # 空图不喂引擎也不叫替身，直接报没检出；三层状态保持已记录值，不为诊断加载
    if not data:
        return _diag_result(_tried_engine_state(), False, 0, [], "empty_image", "")
    # 测试注入替身，不算真实引擎，按 ready 报，分层状态和命中层留空串
    if decoder is not None:
        try:
            result = decoder(data)
        except Exception as exc:  # noqa: BLE001 - 替身异常当未检出，不误禁
            return _diag_result(ENGINE_READY, False, 0, [], type(exc).__name__, "")
        box_count, payloads = _decoder_counts(result)
        return _diag_result(ENGINE_READY, _has_items(result), box_count, payloads, "", "")
    image = _bgr_from_bytes(data)
    # 解不出 BGR 说明这些字节不是图片，三级都不调用；状态只报已试过的层，
    # 不能把「图坏了」写成引擎 missing
    if image is None:
        return _diag_result(_tried_engine_state(), False, 0, [], "bad_image", "")
    return _diagnose_three_layers(image)


def _diagnose_three_layers(image) -> dict:
    """真实三级诊断：微信、zxing、QReader 按顺序跑，命中即停，异常不中断诊断。"""
    layer, box_count, payloads, error = _wechat_diagnose(image)
    # 微信层命中就不跑后两级，也不为诊断提前加载它们
    if layer:
        return _diag_from_layer(layer, box_count, payloads, error)
    layer, box_count, payloads, zxing_error = _zxing_diagnose(image)
    # 这一层没抛异常时留着前一级的类型名，页面才知道是谁失败后兜住的
    if not zxing_error:
        zxing_error = error
    # zxing 命中同样不加载第三级
    if layer:
        return _diag_from_layer(layer, box_count, payloads, zxing_error)
    layer, box_count, payloads, qreader_error = _qreader_diagnose(image)
    # 最后一级没抛异常就沿用前面失败层的类型名，三级都异常时留最后一级的类型名
    if not qreader_error:
        qreader_error = zxing_error
    # 有框或有非空文本都算 QReader 层命中
    if layer:
        return _diag_from_layer(layer, box_count, payloads, qreader_error)
    # 三级都未检出：命中层留空串，错误名保留最后一层失败的类型名
    return _diag_result(_tried_engine_state(), False, 0, [], qreader_error, "")


def _diag_from_layer(layer: str, box_count: int, payloads: list, error: str) -> dict:
    """命中层的诊断结果。总状态按已经试过的层算，未走到的层留空串。"""
    return _diag_result(_tried_engine_state(), True, box_count, payloads, error, layer)


def _wechat_diagnose(image) -> tuple:
    """微信层诊断：解出非空文本就报命中层，异常只留类型名，缺 contrib 直接跳过。"""
    detector = _load_wechat()
    # 这一层缺 contrib 或模型构造失败时跳过，交给后两级兜底
    if detector is None:
        return "", 0, [], ""
    try:
        texts = _wechat_texts(detector, image)
    except Exception as exc:  # noqa: BLE001 - 检测器异常不处置消息，只记类型名继续后级
        return "", 0, [], type(exc).__name__
    payloads = _payload_list(texts)
    # 只有定位点没有文本时不算这一层命中，继续后级
    if not payloads:
        return "", 0, [], ""
    # 数量按截断前的非空文本条数报，载荷才截到 120 字、3 条
    return _LAYER_WECHAT, _nonblank_text_count(texts), payloads, ""


def _zxing_diagnose(image) -> tuple:
    """zxing 层诊断：白名单格式的非空文本才算命中，异常只留类型名。"""
    module = _load_zxing()
    # 这一层没导入成功时跳过，交给 QReader 兜底
    if module is None:
        return "", 0, [], ""
    try:
        texts = _zxing_texts(module, image)
    except Exception as exc:  # noqa: BLE001 - 解码异常不处置消息，只记类型名继续后级
        return "", 0, [], type(exc).__name__
    # 一维商品码和空文本在取文本时就丢掉了，剩下的都算这一层的数量
    if not texts:
        return "", 0, [], ""
    return _LAYER_ZXING, len(texts), _payload_list(texts), ""


def _qreader_diagnose(image) -> tuple:
    """QReader 层诊断：走到这一级才把 BGR 转 RGB，有框或有非空文本都算命中。"""
    reader = _load_qreader()
    # 这一层没起来就跳过，总状态按已试过的层算
    if reader is None:
        return "", 0, [], ""
    try:
        box_count, payloads = _qreader_counts(reader, _bgr_to_rgb(image))
    except Exception as exc:  # noqa: BLE001 - 检测模型异常不能误禁，只记类型名
        return "", 0, [], type(exc).__name__
    # 有框没文本也算命中，这时候载荷是空列表
    if box_count == 0 and not payloads:
        return "", 0, [], ""
    return _LAYER_QREADER, box_count, payloads, ""


def _decoder_counts(result: object) -> tuple:
    """从替身返回里数框和载荷。字符串算载荷，其它元素算框。"""
    # 布尔和空结果既没框也没载荷
    if result is None or isinstance(result, bool):
        return 0, []
    # 直接给一段文本
    if isinstance(result, (str, bytes)):
        return 0, _payload_list([result])
    try:
        items = list(result)
    except TypeError:
        # 单个框对象也算一个框
        return 1, []
    boxes = 0
    payloads = []
    for item in items:
        # 文本行算载荷，别的都当框
        if isinstance(item, str):
            payloads.append(item)
            continue
        boxes += 1
    return boxes, _payload_list(payloads)


def _count_items(value: object) -> int:
    """能数长度就数，单个框对象算一个。"""
    try:
        return len(value)
    except TypeError:
        # 单个框对象也算一个框
        return 1


def _nonblank_text_count(values: object) -> int:
    """数去空白后非空的文本条数。空串是定位点或空载荷，不计入命中层数量。"""
    count = 0
    for item in _text_items(values):
        # 没有文本的定位点不算一条检出
        if str(item).strip():
            count += 1
    return count


def _payload_list(values: object) -> list:
    """收载荷：丢掉空串、每条截断 120 字、最多留 3 条。"""
    payloads = []
    for item in _text_items(values):
        text = str(item).strip()
        # 空文本不是载荷
        if not text:
            continue
        payloads.append(text[:_PAYLOAD_MAX_LEN])
        # 页面只看前三条，多了不传
        if len(payloads) >= _PAYLOAD_MAX_ITEMS:
            break
    return payloads


def _text_items(values: object) -> list:
    """把引擎或替身的返回收成待检查的文本项。"""
    # 没有输出
    if values is None:
        return []
    # 直接给一段文本
    if isinstance(values, (str, bytes)):
        return [values]
    try:
        return list(values)
    except TypeError:
        # 单个载荷对象也算一条
        return [values]


def _diag_result(
    engine: str, found: bool, box_count: int, payloads: list, error: str, layer: str
) -> dict:
    """拼诊断结果。九个键一个不少，调用方读不到字段也不会 KeyError。"""
    # 三个分层状态报本进程已经记下的值：还没试过的层是空串，页面显示「本次未加载」，
    # 不能为了凑字段在这里触发加载
    return {
        "engine": engine,
        "wechat": _wechat_state,
        "zxing": _zxing_state,
        "qreader": _qreader_state,
        "layer": layer,
        "found": found,
        "box_count": box_count,
        "payloads": payloads,
        "error": error,
    }


def _warn_engine_once() -> None:
    """引擎总状态不是 ready 时只记一次 warning，写明状态，免得漏检没有痕迹。"""
    global _engine_warned
    # 已经记过就不再刷
    if _engine_warned:
        return
    # 只看已试过的层，不能为了报状态把没走到的后级提前加载
    state = _total_state(_tried_states())
    # 还有层能用就不算引擎不可用，这条 warning 不记
    if state == ENGINE_READY:
        return
    _engine_warned = True
    _log.warning("[rules] qr engine not ready state=%s", state)
