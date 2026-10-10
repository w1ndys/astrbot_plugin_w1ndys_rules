# 原图 OCR：注入 reader；坏图和异常当没字，不误禁。

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business import forbidden_ocr
from astrbot_plugin_w1ndys_rules.business.forbidden_ocr import (
    _collect_texts,
    _join_texts,
    ocr_diagnose_bytes,
    ocr_text_from_b64,
    ocr_text_from_bytes,
)


class FakeOutput:
    def __init__(self, txts=None) -> None:
        self.txts = txts


class OcrTextTest(unittest.TestCase):
    def test_reader_string(self) -> None:
        text = ocr_text_from_bytes(b"xx", reader=lambda _data: "6m3p.cc 上面约的")
        self.assertEqual(text, "6m3p.cc 上面约的")

    def test_reader_boom_is_empty(self) -> None:
        def boom(_data):
            raise RuntimeError("bad")

        self.assertEqual(ocr_text_from_bytes(b"xx", reader=boom), "")

    def test_empty_bytes(self) -> None:
        self.assertEqual(ocr_text_from_bytes(b"", reader=lambda _data: "字"), "")

    def test_empty_b64(self) -> None:
        self.assertEqual(ocr_text_from_b64("", reader=lambda _data: "字"), "")

    def test_b64_without_padding(self) -> None:
        text = ocr_text_from_b64("YQ", reader=lambda _data: "可见字")
        self.assertEqual(text, "可见字")


class CollectTextsTest(unittest.TestCase):
    def test_txts_attr(self) -> None:
        self.assertEqual(_join_texts(FakeOutput(["我都在", "6m3p.cc"])), "我都在\n6m3p.cc")

    def test_old_tuple_rows(self) -> None:
        rows = [[[0, 0], "全国随时随地都可以玩", 0.9]]
        self.assertEqual(_join_texts((rows, 0.1)), "全国随时随地都可以玩")

    def test_none(self) -> None:
        self.assertEqual(_collect_texts(None), [])


# sys.modules 里原本没有这个键时记下的哨兵，还原时按它决定删不删
_MISSING = object()


class _BoomRapidOCR:
    """建实例就炸的替身，模拟权重加载失败。"""

    def __init__(self) -> None:
        raise RuntimeError("bad weights")


class _QuietLog:
    """吞日志的替身，避免测试碰真实 AstrBot 日志代理。"""

    def __init__(self) -> None:
        self.warnings = []

    def warning(self, template: str, *args) -> None:
        """只记账，不输出。"""
        self.warnings.append(template)

    def info(self, template: str, *args) -> None:
        """只记账，不输出。"""
        pass


class OcrDiagnoseTest(unittest.TestCase):
    """OCR 诊断：引擎状态和文字要分开报，别把没装引擎说成没字。"""

    def setUp(self) -> None:
        # 诊断读模块级缓存，先存旧值，测完还原，免得污染别的测试
        self._saved = (
            forbidden_ocr._engine,
            forbidden_ocr._engine_failed,
            forbidden_ocr._engine_init_failed,
            forbidden_ocr._log,
            sys.modules.get("rapidocr", _MISSING),
            sys.modules.get("rapidocr_onnxruntime", _MISSING),
        )
        forbidden_ocr._engine = None
        forbidden_ocr._engine_failed = False
        forbidden_ocr._engine_init_failed = False
        forbidden_ocr._log = _QuietLog()

    def tearDown(self) -> None:
        (
            forbidden_ocr._engine,
            forbidden_ocr._engine_failed,
            forbidden_ocr._engine_init_failed,
            forbidden_ocr._log,
            saved_new,
            saved_old,
        ) = self._saved
        self._restore_module("rapidocr", saved_new)
        self._restore_module("rapidocr_onnxruntime", saved_old)

    def _restore_module(self, name: str, saved: object) -> None:
        """原来没装这个包就删掉，别把假模块留给后面的测试。"""
        # 单测环境本来就没有这个键
        if saved is _MISSING:
            sys.modules.pop(name, None)
            return
        sys.modules[name] = saved

    def _hide_engines(self) -> None:
        """两个包名都藏起来，模拟本机没装 OCR 引擎。"""
        sys.modules["rapidocr"] = None
        sys.modules["rapidocr_onnxruntime"] = None

    def test_reader_text_ready(self) -> None:
        diag = ocr_diagnose_bytes(b"xx", reader=lambda _data: "可见字")
        self.assertEqual(diag["engine"], "ready")
        self.assertEqual(diag["text"], "可见字")
        self.assertEqual(diag["error"], "")

    def test_reader_boom_ready_and_no_text(self) -> None:
        def boom(_data):
            raise RuntimeError("bad")

        diag = ocr_diagnose_bytes(b"xx", reader=boom)
        self.assertEqual(diag["engine"], "ready")
        self.assertEqual(diag["text"], "")
        self.assertEqual(diag["error"], "RuntimeError")

    def test_reader_empty_result_keeps_ready(self) -> None:
        diag = ocr_diagnose_bytes(b"xx", reader=lambda _data: None)
        self.assertEqual(diag["engine"], "ready")
        self.assertEqual(diag["text"], "")
        self.assertEqual(diag["error"], "")

    def test_missing_engine(self) -> None:
        self._hide_engines()
        diag = ocr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "missing")
        self.assertEqual(diag["text"], "")

    def test_init_failed_engine(self) -> None:
        fake = types.ModuleType("rapidocr")
        fake.RapidOCR = _BoomRapidOCR
        sys.modules["rapidocr"] = fake
        # 新包名在时不会去试旧包，这里只需要新包名
        sys.modules.pop("rapidocr_onnxruntime", None)
        diag = ocr_diagnose_bytes(b"xx")
        self.assertEqual(diag["engine"], "init_failed")
        self.assertEqual(diag["text"], "")

    def test_empty_bytes_not_read(self) -> None:
        self._hide_engines()
        diag = ocr_diagnose_bytes(b"")
        self.assertEqual(diag["text"], "")
        self.assertEqual(diag["error"], "empty_image")
