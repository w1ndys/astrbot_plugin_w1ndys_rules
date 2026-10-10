# 二维码层：注入 decoder；坏图和异常当未检出，不误禁。

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


class _BoomQReader:
    """建实例就炸的替身，模拟权重加载失败。"""

    def __init__(self) -> None:
        raise RuntimeError("bad weights")


class _WarnLog:
    """只记 warning 文案的替身日志，用来数引擎不可用报了几次。"""

    def __init__(self) -> None:
        self.warnings = []

    def warning(self, template: str, *args) -> None:
        """把 %s 占位填好存下来。"""
        self.warnings.append(template % args if args else template)


class QrDiagnoseTest(unittest.TestCase):
    """诊断结果：引擎状态和检出要分开报，别把没装库说成无码。"""

    def setUp(self) -> None:
        # 诊断读模块级缓存，先存旧值，测完还原，免得污染别的测试
        self._saved = (
            forbidden_qr._qreader,
            forbidden_qr._qreader_failed,
            forbidden_qr._qreader_init_failed,
            forbidden_qr._qreader_warned,
            forbidden_qr._bytes_to_rgb,
            forbidden_qr._log,
            sys.modules.get("qreader", _MISSING),
        )
        self._log = _WarnLog()
        forbidden_qr._qreader = None
        forbidden_qr._qreader_failed = False
        forbidden_qr._qreader_init_failed = False
        forbidden_qr._qreader_warned = False
        forbidden_qr._log = self._log

    def tearDown(self) -> None:
        (
            forbidden_qr._qreader,
            forbidden_qr._qreader_failed,
            forbidden_qr._qreader_init_failed,
            forbidden_qr._qreader_warned,
            forbidden_qr._bytes_to_rgb,
            forbidden_qr._log,
            saved_module,
        ) = self._saved
        # 原来没装 qreader 就删掉，别把假模块留给后面的测试
        if saved_module is _MISSING:
            sys.modules.pop("qreader", None)
            return
        sys.modules["qreader"] = saved_module

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
        forbidden_qr._qreader = FakeReader(boxes=[], texts=[])
        forbidden_qr._bytes_to_rgb = lambda _data: object()
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "ready")
        self.assertFalse(diag["found"])
        self.assertEqual(diag["box_count"], 0)
        self.assertEqual(diag["payloads"], [])

    def test_engine_ready_with_boxes(self) -> None:
        forbidden_qr._qreader = FakeReader(boxes=[{"x": 1}], texts=[])
        forbidden_qr._bytes_to_rgb = lambda _data: object()
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "ready")
        self.assertTrue(diag["found"])
        self.assertEqual(diag["box_count"], 1)

    def test_import_failure_is_missing(self) -> None:
        sys.modules["qreader"] = None
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "missing")
        self.assertFalse(diag["found"])

    def test_init_failure_is_init_failed(self) -> None:
        fake = types.ModuleType("qreader")
        fake.QReader = _BoomQReader
        sys.modules["qreader"] = fake
        diag = qr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "init_failed")
        self.assertFalse(diag["found"])

    def test_empty_bytes_not_found(self) -> None:
        sys.modules["qreader"] = None
        diag = qr_diagnose_bytes(b"")
        self.assertFalse(diag["found"])
        self.assertEqual(diag["error"], "empty_image")

    def test_hot_path_warns_engine_once(self) -> None:
        sys.modules["qreader"] = None
        qr_found_in_bytes(b"xx")
        qr_found_in_bytes(b"xx")
        # 每张图都记一条会刷屏，只认第一条
        self.assertEqual(len(self._log.warnings), 1)
        self.assertIn("missing", self._log.warnings[0])
