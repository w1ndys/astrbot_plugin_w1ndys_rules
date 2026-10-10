# 二维码层：注入 decoder；坏图和异常当未检出，不误禁。
# 三级引擎全部打桩，本机有没有 OpenCV contrib、zxing-cpp、QReader 都不影响结果。

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business import forbidden_qr
from astrbot_plugin_w1ndys_rules.business.forbidden_qr import (
    _has_items,
    _reader_hit,
    qr_diagnose_bytes,
    qr_engine_state,
    qr_found_in_b64,
    qr_found_in_bytes,
)


class FakeReader:
    """只提供 detect 或 decode 的替身。"""

    def __init__(self, boxes=None, texts=None) -> None:
        self.boxes = boxes
        self.texts = texts

    def detect(self, image=None):
        """返回框列表。"""
        return self.boxes

    def detect_and_decode(self, image=None):
        """返回文本列表。"""
        return self.texts


class QrFoundTest(unittest.TestCase):
    def test_decoder_true(self) -> None:
        self.assertTrue(qr_found_in_bytes(b"xx", decoder=lambda _data: True))

    def test_decoder_boom_is_false(self) -> None:
        def boom(_data):
            raise RuntimeError("bad")

        self.assertFalse(qr_found_in_bytes(b"xx", decoder=boom))

    def test_empty_bytes(self) -> None:
        self.assertFalse(qr_found_in_bytes(b"", decoder=lambda _data: True))

    def test_empty_b64(self) -> None:
        self.assertFalse(qr_found_in_b64("", decoder=lambda _data: True))

    def test_b64_without_padding(self) -> None:
        # YQ== 去掉 padding 仍是字母 a
        self.assertTrue(qr_found_in_b64("YQ", decoder=lambda _data: True))


class ReaderHitTest(unittest.TestCase):
    def test_detect_boxes(self) -> None:
        reader = FakeReader(boxes=[{"x": 1}])
        self.assertTrue(_reader_hit(reader, object()))

    def test_detect_empty(self) -> None:
        reader = FakeReader(boxes=[])
        self.assertFalse(_reader_hit(reader, object()))

    def test_decode_text(self) -> None:
        reader = FakeReader(texts=["http://x"])

        reader.detect = None
        self.assertTrue(_reader_hit(reader, object()))

    def test_has_items_none(self) -> None:
        self.assertFalse(_has_items(None))
        self.assertTrue(_has_items((1,)))


# sys.modules 里原本没有这个键时记下的哨兵，还原时按它决定删不删
_MISSING = object()

# 三级加载要导入的模块名。打桩和还原都按这份名单走。
_ENGINE_MODULES = ("cv2", "cv2.wechat_qrcode", "zxingcpp", "qreader")


def _hide_module(name: str) -> None:
    """把模块占位成 None，import 直接失败，用来模拟本机没装这个库。"""
    sys.modules[name] = None


def _fake_module(name: str) -> types.ModuleType:
    """造一个假模块塞进 sys.modules，用来模拟库已装好。"""
    fake = types.ModuleType(name)
    sys.modules[name] = fake
    return fake


def _fake_wechat_module(wechat_cls: object) -> None:
    """造假 cv2 包和 cv2.wechat_qrcode 子模块，让微信层能导入成功。"""
    fake_cv2 = _fake_module("cv2")
    fake_wechat = _fake_module("cv2.wechat_qrcode")
    fake_wechat.WeChatQRCode = wechat_cls
    fake_cv2.wechat_qrcode = fake_wechat


class _BoomQReader:
    """建实例就炸的 QReader 替身，模拟权重加载失败。"""

    def __init__(self) -> None:
        raise RuntimeError("bad weights")


class _BoomWeChat:
    """建实例就炸的微信检测器替身，模拟 contrib 模型构造失败。"""

    def __init__(self) -> None:
        raise RuntimeError("bad model")


class _FakeWeChat:
    """能构造的微信检测器替身，代表容器里 contrib 装好了。"""

    def __init__(self) -> None:
        """无参构造成功，和容器的 WeChatQRCode() 一致。"""
        self.created = True


class _WeChatStub:
    """微信检测器替身：detectAndDecode 返回预先定好的文本和定位点。"""

    def __init__(self, texts=(), points=(), boom=False) -> None:
        self.texts = tuple(texts)
        self.points = tuple(points)
        self.boom = boom

    def detectAndDecode(self, image=None):
        """按构造时给的文本和定位点返回二元组，和解出的真实接口一致。"""
        # 模拟检测器异常：热路径要当未检出并继续后级
        if self.boom:
            raise RuntimeError("wechat boom")
        return self.texts, self.points


class _ZxingItem:
    """zxing 返回项替身：只有 format 和 text 两个字段。"""

    def __init__(self, fmt, text) -> None:
        self.format = fmt
        self.text = text


class _FakeBarcodeFormat:
    """zxing 格式枚举替身。用位值模拟绑定枚举，`|` 拼白名单才跑得通。"""

    QRCode = 1
    MicroQRCode = 2
    RMQRCode = 4
    Aztec = 8
    DataMatrix = 16
    PDF417 = 32
    # 一维商品码：库默认会认，但本功能不传入也不采纳
    EAN13 = 64


class _PartialBarcodeFormat:
    """只带两个枚举的绑定替身，用来验证缺枚举时跳过而不是整层失败。"""

    QRCode = 1
    DataMatrix = 16


class _ZxingStub:
    """zxing 模块替身：记下每次调用的参数，返回预先定好的结果项。"""

    def __init__(self, results=(), formats_enum=_FakeBarcodeFormat) -> None:
        self.results = list(results)
        self.BarcodeFormat = formats_enum
        self.calls = []

    def read_barcodes(self, image, **kwargs):
        """记一次调用参数后返回结果项列表。"""
        self.calls.append(kwargs)
        return self.results


class _ZxingBoomStub(_ZxingStub):
    """读码就炸的 zxing 替身，模拟解码异常。"""

    def read_barcodes(self, image, **kwargs):
        """直接抛异常，热路径要当未检出并继续后级。"""
        raise RuntimeError("zxing boom")


class _BoomReader:
    """detect 就炸的 QReader 替身，模拟检测模型异常。"""

    def detect(self, image=None):
        """抛异常，热路径要当未检出。"""
        raise RuntimeError("qreader boom")


class _WarnLog:
    """只记 warning 文案的替身日志，用来数引擎不可用报了几次。"""

    def __init__(self) -> None:
        self.warnings = []

    def warning(self, template: str, *args) -> None:
        """把 %s 占位填好存下来。"""
        self.warnings.append(template % args if args else template)


class _EngineStubTest(unittest.TestCase):
    """三级引擎缓存的公共打桩：测前全部藏掉，测完还原，免得污染别的测试。"""

    def setUp(self) -> None:
        # 实例、分层状态和 warning 标记都是模块级，先存旧值再清零
        self._saved = (
            forbidden_qr._wechat,
            forbidden_qr._wechat_state,
            forbidden_qr._zxing,
            forbidden_qr._zxing_state,
            forbidden_qr._qreader,
            forbidden_qr._qreader_state,
            forbidden_qr._engine_warned,
            forbidden_qr._bytes_to_rgb,
            forbidden_qr._bgr_from_bytes,
            forbidden_qr._bgr_to_rgb,
            forbidden_qr._log,
        )
        # 本机这几个包装没装也算环境状态，一并存下来
        self._saved_modules = {
            name: sys.modules.get(name, _MISSING) for name in _ENGINE_MODULES
        }
        self._log = _WarnLog()
        forbidden_qr._wechat = None
        forbidden_qr._wechat_state = ""
        forbidden_qr._zxing = None
        forbidden_qr._zxing_state = ""
        forbidden_qr._qreader = None
        forbidden_qr._qreader_state = ""
        forbidden_qr._engine_warned = False
        forbidden_qr._log = self._log
        # 三级默认都当没装，哪一层要可用由各条测试自己放替身
        for name in _ENGINE_MODULES:
            _hide_module(name)

    def tearDown(self) -> None:
        (
            forbidden_qr._wechat,
            forbidden_qr._wechat_state,
            forbidden_qr._zxing,
            forbidden_qr._zxing_state,
            forbidden_qr._qreader,
            forbidden_qr._qreader_state,
            forbidden_qr._engine_warned,
            forbidden_qr._bytes_to_rgb,
            forbidden_qr._bgr_from_bytes,
            forbidden_qr._bgr_to_rgb,
            forbidden_qr._log,
        ) = self._saved
        for name in _ENGINE_MODULES:
            saved = self._saved_modules[name]
            # 本来没装的键要删掉，别把假模块留给后面的测试
            if saved is _MISSING:
                sys.modules.pop(name, None)
                continue
            sys.modules[name] = saved


class QrDiagnoseTest(_EngineStubTest):
    """诊断结果：引擎状态和检出要分开报，别把没装库说成无码。"""

    def test_decoder_boxes_ready_and_found(self) -> None:
        diag = qr_diagnose_bytes(b"xx", decoder=lambda _data: [{"x": 1}])
        self.assertEqual(diag["engine"], "ready")
        self.assertTrue(diag["found"])
        self.assertEqual(diag["box_count"], 1)
        self.assertEqual(diag["error"], "")

    def test_decoder_payloads_cut_to_three(self) -> None:
        texts = ["码" * 200, "b", "c", "d"]
        diag = qr_diagnose_bytes(b"xx", decoder=lambda _data: texts)
        self.assertEqual(diag["engine"], "ready")
        self.assertTrue(diag["found"])
        self.assertEqual(diag["payloads"], ["码" * 120, "b", "c"])

    def test_decoder_boom_ready_and_not_found(self) -> None:
        def boom(_data):
            raise RuntimeError("bad")

        diag = qr_diagnose_bytes(b"xx", decoder=boom)
        self.assertEqual(diag["engine"], "ready")
        self.assertFalse(diag["found"])
        self.assertEqual(diag["error"], "RuntimeError")

    def test_engine_ready_without_code(self) -> None:
        # 第三级已有实例，分层状态也要跟着报 ready
        forbidden_qr._qreader = FakeReader(boxes=[], texts=[])
        forbidden_qr._qreader_state = "ready"
        forbidden_qr._bytes_to_rgb = lambda _data: object()
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "ready")
        self.assertFalse(diag["found"])
        self.assertEqual(diag["box_count"], 0)
        self.assertEqual(diag["payloads"], [])

    def test_engine_ready_with_boxes(self) -> None:
        forbidden_qr._qreader = FakeReader(boxes=[{"x": 1}], texts=[])
        forbidden_qr._qreader_state = "ready"
        forbidden_qr._bytes_to_rgb = lambda _data: object()
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "ready")
        self.assertTrue(diag["found"])
        self.assertEqual(diag["box_count"], 1)

    def test_import_failure_is_missing(self) -> None:
        # 三级都没装，总状态只能报 missing
        _hide_module("qreader")
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "missing")
        self.assertFalse(diag["found"])
        self.assertEqual(forbidden_qr._qreader_state, "missing")

    def test_init_failure_is_init_failed(self) -> None:
        fake = _fake_module("qreader")
        fake.QReader = _BoomQReader
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "init_failed")
        self.assertFalse(diag["found"])

    def test_empty_bytes_not_found(self) -> None:
        diag = qr_diagnose_bytes(b"")
        self.assertFalse(diag["found"])
        self.assertEqual(diag["error"], "empty_image")

    def test_hot_path_warns_engine_once(self) -> None:
        # 坏字节解不出图，不会走到引擎；这里给一份能解码的图，才测得到引擎缺失的 warning
        forbidden_qr._bgr_from_bytes = lambda _data: object()
        qr_found_in_bytes(b"xx")
        qr_found_in_bytes(b"xx")
        # 每张图都记一条会刷屏，只认第一条
        self.assertEqual(len(self._log.warnings), 1)
        self.assertIn("missing", self._log.warnings[0])


class QrEngineStateTest(_EngineStubTest):
    """分层加载和总状态：一层不可用不能拖累别的层。"""

    def test_wechat_missing_zxing_ready_is_ready(self) -> None:
        # 微信层没装、QReader 也没装，只要 zxing 能用，总状态就是 ready
        _hide_module("cv2")
        _fake_module("zxingcpp")
        self.assertEqual(qr_engine_state(), "ready")
        self.assertEqual(forbidden_qr._wechat_state, "missing")
        self.assertEqual(forbidden_qr._zxing_state, "ready")

    def test_wechat_ready_when_contrib_present(self) -> None:
        # cv2 带 contrib 时微信层就绪，构造出的实例被复用
        _fake_wechat_module(_FakeWeChat)
        self.assertIsNotNone(forbidden_qr._load_wechat())
        self.assertEqual(forbidden_qr._wechat_state, "ready")
        self.assertEqual(qr_engine_state(), "ready")

    def test_all_layers_missing_is_missing(self) -> None:
        # 三级导入都失败才算缺失，warning 每进程只记一条
        self.assertEqual(qr_engine_state(), "missing")
        self.assertEqual(forbidden_qr._qreader_state, "missing")
        # 坏字节不会进三级，换成能解码的图才走得到「引擎缺失」这条 warning
        forbidden_qr._bgr_from_bytes = lambda _data: object()
        qr_found_in_bytes(b"xx")
        qr_found_in_bytes(b"xx")
        self.assertEqual(len(self._log.warnings), 1)
        self.assertIn("state=missing", self._log.warnings[0])

    def test_wechat_construct_failure_is_init_failed(self) -> None:
        # 库导入成功但构造失败要报 init_failed，不能冤枉成没装库
        _fake_wechat_module(_BoomWeChat)
        self.assertIsNone(forbidden_qr._load_wechat())
        self.assertEqual(forbidden_qr._wechat_state, "init_failed")
        self.assertEqual(qr_engine_state(), "init_failed")

    def test_one_layer_init_failure_keeps_other_ready(self) -> None:
        # QReader 构造失败不影响 zxing 层，总状态仍算 ready
        fake = _fake_module("qreader")
        fake.QReader = _BoomQReader
        _fake_module("zxingcpp")
        self.assertIsNone(forbidden_qr._load_qreader())
        self.assertEqual(forbidden_qr._qreader_state, "init_failed")
        # 补试前两级之后 zxing 才有着落，总状态仍报 ready
        self.assertEqual(qr_engine_state(), "ready")
        self.assertEqual(forbidden_qr._zxing_state, "ready")

    def test_load_result_reused_once(self) -> None:
        # 一层失败后不再重试：后面放上真模块，这一层仍按上次结论回空
        _hide_module("zxingcpp")
        self.assertIsNone(forbidden_qr._load_zxing())
        _fake_module("zxingcpp")
        self.assertIsNone(forbidden_qr._load_zxing())
        self.assertEqual(forbidden_qr._zxing_state, "missing")

    def test_hot_path_bad_image_leaves_layers_untried(self) -> None:
        # 热路径拿到的字节不是图片时三级都不跑，状态留空串说明一层都没加载
        forbidden_qr._bgr_from_bytes = lambda _data: None
        self.assertFalse(qr_found_in_bytes(b"xx"))
        self.assertEqual(forbidden_qr._wechat_state, "")
        self.assertEqual(forbidden_qr._zxing_state, "")
        self.assertEqual(forbidden_qr._qreader_state, "")


class QrLayerOrderTest(_EngineStubTest):
    """热路径三级顺序：前一级检出就不跑后面的级，一层异常不拖累后面的层。"""

    def setUp(self) -> None:
        super().setUp()
        # 三级都吃 BGR 数组，替身给个占位对象，不跑真 OpenCV
        forbidden_qr._bgr_from_bytes = lambda _data: object()
        forbidden_qr._bgr_to_rgb = lambda _image: object()

    def test_decoder_path_touches_no_layer(self) -> None:
        # 注入替身时三级加载函数都不该跑，状态留空串说明一层都没导入
        self.assertTrue(qr_found_in_bytes(b"xx", decoder=lambda _data: True))
        self.assertEqual(forbidden_qr._wechat_state, "")
        self.assertEqual(forbidden_qr._zxing_state, "")
        self.assertEqual(forbidden_qr._qreader_state, "")

    def test_wechat_text_skips_later_layers(self) -> None:
        # 微信层解出文本就检出：zxing 替身不该被调用，qreader 模块也不该被导入
        forbidden_qr._wechat = _WeChatStub(texts=("http://wechat",))
        forbidden_qr._wechat_state = "ready"
        zxing = _ZxingStub([_ZxingItem(_FakeBarcodeFormat.QRCode, "http://zxing")])
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))
        self.assertEqual(zxing.calls, [])
        self.assertEqual(forbidden_qr._qreader_state, "")

    def test_wechat_points_only_goes_to_zxing(self) -> None:
        # 微信层只有定位点没文本时不算检出，继续用 zxing 兜底
        forbidden_qr._wechat = _WeChatStub(texts=("",), points=({"x": 1},))
        forbidden_qr._wechat_state = "ready"
        forbidden_qr._zxing = _ZxingStub(
            [_ZxingItem(_FakeBarcodeFormat.QRCode, " http://zxing ")]
        )
        forbidden_qr._zxing_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))

    def test_wechat_boom_goes_to_zxing(self) -> None:
        # 微信层抛异常时不当检出，交给 zxing 接着解
        forbidden_qr._wechat = _WeChatStub(boom=True)
        forbidden_qr._wechat_state = "ready"
        zxing = _ZxingStub([_ZxingItem(_FakeBarcodeFormat.QRCode, "http://zxing")])
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))
        self.assertEqual(len(zxing.calls), 1)

    def test_zxing_text_skips_qreader(self) -> None:
        # zxing 解出文本就不构造 QReader，第三级状态留空串说明没加载
        forbidden_qr._wechat_state = "missing"
        forbidden_qr._zxing = _ZxingStub(
            [_ZxingItem(_FakeBarcodeFormat.QRCode, "http://zxing")]
        )
        forbidden_qr._zxing_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))
        self.assertEqual(forbidden_qr._qreader_state, "")
        self.assertIsNone(forbidden_qr._qreader)

    def test_zxing_call_uses_whitelist_only(self) -> None:
        # 只传二维白名单：不传一维码，也不传 try_harder、try_rotate、try_invert
        zxing = _ZxingStub()
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertFalse(qr_found_in_bytes(b"xx"))
        self.assertEqual(len(zxing.calls), 1)
        self.assertEqual(list(zxing.calls[0]), ["formats"])
        self.assertEqual(
            zxing.calls[0]["formats"],
            _FakeBarcodeFormat.QRCode
            | _FakeBarcodeFormat.MicroQRCode
            | _FakeBarcodeFormat.RMQRCode
            | _FakeBarcodeFormat.Aztec
            | _FakeBarcodeFormat.DataMatrix
            | _FakeBarcodeFormat.PDF417,
        )

    def test_zxing_one_d_code_is_not_found(self) -> None:
        # EAN 这类一维商品码既不传入也不采纳，免得普通商品照片被判违禁
        zxing = _ZxingStub([_ZxingItem(_FakeBarcodeFormat.EAN13, "6901234567892")])
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertFalse(qr_found_in_bytes(b"xx"))
        self.assertEqual(zxing.calls[0]["formats"] & _FakeBarcodeFormat.EAN13, 0)

    def test_zxing_blank_text_is_not_found(self) -> None:
        # 格式在白名单里但文本是空白，仍不算检出
        forbidden_qr._zxing = _ZxingStub([_ZxingItem(_FakeBarcodeFormat.QRCode, "  ")])
        forbidden_qr._zxing_state = "ready"
        self.assertFalse(qr_found_in_bytes(b"xx"))

    def test_zxing_partial_binding_skips_missing_enum(self) -> None:
        # 绑定缺枚举时跳过它，剩下能拼的先拼，不整层失败
        zxing = _ZxingStub(
            [_ZxingItem(_PartialBarcodeFormat.QRCode, "http://zxing")],
            formats_enum=_PartialBarcodeFormat,
        )
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))
        self.assertEqual(
            zxing.calls[0]["formats"],
            _PartialBarcodeFormat.QRCode | _PartialBarcodeFormat.DataMatrix,
        )

    def test_zxing_without_enum_is_not_found(self) -> None:
        # 绑定没有格式枚举就限不了格式，按未检出处理，不误采纳一维码
        zxing = _ZxingStub([_ZxingItem(1, "http://zxing")], formats_enum=None)
        forbidden_qr._zxing = zxing
        forbidden_qr._zxing_state = "ready"
        self.assertFalse(qr_found_in_bytes(b"xx"))
        self.assertEqual(zxing.calls, [{}])

    def test_qreader_box_only_is_found(self) -> None:
        # 前两级都没解出时，QReader 有框没文本也算检出
        forbidden_qr._wechat_state = "missing"
        forbidden_qr._zxing_state = "missing"
        forbidden_qr._qreader = FakeReader(boxes=[{"x": 1}], texts=[])
        forbidden_qr._qreader_state = "ready"
        self.assertTrue(qr_found_in_bytes(b"xx"))

    def test_all_layers_boom_is_not_found(self) -> None:
        # 三级各自抛异常都只算未检出，不能误禁
        forbidden_qr._wechat = _WeChatStub(boom=True)
        forbidden_qr._wechat_state = "ready"
        forbidden_qr._zxing = _ZxingBoomStub()
        forbidden_qr._zxing_state = "ready"
        forbidden_qr._qreader = _BoomReader()
        forbidden_qr._qreader_state = "ready"
        self.assertFalse(qr_found_in_bytes(b"xx"))
