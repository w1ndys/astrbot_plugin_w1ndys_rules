# 原图 OCR：注入 reader；坏图和异常当没字，不误禁。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_ocr import (
    _collect_texts,
    _join_texts,
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
