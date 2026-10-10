# 业务层：本地二维码检出。用 QReader；没装或失败当未检出，不误禁。
# 检出即违禁，不看载荷。测试可传入 decoder。
# 诊断结果只给测试页和日志用，热路径仍只看布尔。

import base64
import io

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

_qreader = None
_qreader_failed = False
# 权重加载失败和没装库要分开报，页面才好判断漏检原因
_qreader_init_failed = False
# 引擎不可用的 warning 只记一次，避免每张图刷同一条日志
_qreader_warned = False
# 诊断返回的载荷每条截断 120 字，页面不展示整段二维码内容
_PAYLOAD_MAX_LEN = 120
# 载荷最多留 3 条，多了对定位漏检没帮助
_PAYLOAD_MAX_ITEMS = 3


def qr_found_in_bytes(data: bytes, decoder=None) -> bool:
    """这组字节里有没有二维码。decoder 命中就 True。"""
    # 空图解不了
    if not data:
        return False
    # 测试注入，不打真实 QReader
    if decoder is not None:
        try:
            return bool(decoder(data))
        except Exception:  # noqa: BLE001 - 注入解码失败当未检出
            return False
    return _qreader_found(data)



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



def _qreader_found(data: bytes) -> bool:
    """用 QReader 检出即 True。库缺失或异常当未检出。"""
    reader = _load_qreader()
    # 没装 QReader 就跳过这一层，但要记一次引擎状态，免得漏检没有痕迹
    if reader is None:
        _warn_engine_once()
        return False
    image = _bytes_to_rgb(data)
    # 转不成图就当没解出来
    if image is None:
        return False
    try:
        return _reader_hit(reader, image)
    except Exception:  # noqa: BLE001 - 解码超时或模型异常不能误禁
        return False


def _load_qreader():
    """懒加载一个 QReader。导入失败只试一次。"""
    global _qreader, _qreader_failed, _qreader_init_failed
    # 已经确定没有这个库
    if _qreader_failed:
        return None
    # 已经建过就复用
    if _qreader is not None:
        return _qreader
    try:
        from qreader import QReader
    except ImportError:
        _qreader_failed = True
        return None
    try:
        _qreader = QReader()
    except Exception:  # noqa: BLE001 - 权重加载失败当没装
        _qreader_failed = True
        # 权重炸了要记下来，诊断才好报 init_failed
        _qreader_init_failed = True
        return None
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



def _bytes_to_rgb(data: bytes):
    """把图片字节收成 QReader 要的 RGB 数组。失败返回 None。"""
    try:
        import numpy as np
        from PIL import Image as PILImage
    except ImportError:
        # 没装 pillow/numpy 就不能喂 QReader，当未检出
        return None

    try:
        pil = PILImage.open(io.BytesIO(data))
        rgb = pil.convert("RGB")
        return np.asarray(rgb)
    except Exception:  # noqa: BLE001 - 坏图当未检出
        return None


def qr_engine_state() -> str:
    """当前二维码引擎状态。诊断字段和热路径日志都用它。"""
    # 已经建好实例就是可用
    if _qreader is not None:
        return ENGINE_READY
    reader = _load_qreader()
    # 这一次拿到实例也算可用
    if reader is not None:
        return ENGINE_READY
    # 权重加载失败和没装库要分开报
    if _qreader_init_failed:
        return ENGINE_INIT_FAILED
    return ENGINE_MISSING


def qr_diagnose_bytes(data: bytes, decoder=None) -> dict:
    """测试页用的二维码诊断：引擎状态、是否检出、框数和载荷。热路径不用它。"""
    # 空图不喂引擎也不叫替身，直接报没检出
    if not data:
        return _diag_result(qr_engine_state(), False, 0, [], "empty_image")
    # 测试注入替身，不算真实引擎，按 ready 报
    if decoder is not None:
        try:
            result = decoder(data)
        except Exception as exc:  # noqa: BLE001 - 替身异常当未检出，不误禁
            return _diag_result(ENGINE_READY, False, 0, [], type(exc).__name__)
        box_count, payloads = _decoder_counts(result)
        return _diag_result(ENGINE_READY, _has_items(result), box_count, payloads, "")
    engine = qr_engine_state()
    # 引擎没跑起来就报否，页面据此提示本次未识别
    if engine != ENGINE_READY:
        return _diag_result(engine, False, 0, [], "")
    return _qr_diagnose_with_reader(engine, data)


def _qr_diagnose_with_reader(engine: str, data: bytes) -> dict:
    """真实 QReader 路径：数框、收载荷。异常只带类型名，不带图片字节。"""
    reader = _load_qreader()
    # 加载失败就按当前状态报否
    if reader is None:
        return _diag_result(qr_engine_state(), False, 0, [], "")
    image = _bytes_to_rgb(data)
    # 转不成图说明这些字节不是图片
    if image is None:
        return _diag_result(engine, False, 0, [], "bad_image")
    box_count = 0
    payloads = []
    try:
        detect = getattr(reader, "detect", None)
        # detect 只回答有几个框
        if callable(detect):
            boxes = detect(image=image)
            # 没返回就是零个框
            if boxes is not None:
                box_count = _count_items(boxes)
        decode = getattr(reader, "detect_and_decode", None)
        # 老接口没有 detect，只能看文本载荷
        if callable(decode):
            payloads = _payload_list(decode(image=image))
    except Exception as exc:  # noqa: BLE001 - 引擎异常当未检出，不误禁
        return _diag_result(engine, False, 0, [], type(exc).__name__)
    # 有框或有载荷都算检出
    found = box_count > 0 or bool(payloads)
    return _diag_result(engine, found, box_count, payloads, "")


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
    engine: str, found: bool, box_count: int, payloads: list, error: str
) -> dict:
    """拼诊断结果。字段名和测试页约定一致，error 不含图片字节。"""
    return {
        "engine": engine,
        "found": found,
        "box_count": box_count,
        "payloads": payloads,
        "error": error,
    }


def _warn_engine_once() -> None:
    """引擎不可用时只记一次 warning，写明状态，免得漏检没有痕迹。"""
    global _qreader_warned
    # 已经记过就不再刷
    if _qreader_warned:
        return
    _qreader_warned = True
    _log.warning("[rules] qr engine not ready state=%s", qr_engine_state())
