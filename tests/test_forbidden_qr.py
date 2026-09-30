# 二维码层：注入 decoder；坏图和异常当未检出，不误禁。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_qr import (
    _has_items,
    _reader_hit,
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
