# 依赖声明：三级二维码解码器都要写进 requirements.txt，按插件市场安装时才不会漏。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QrRequirementsTest(unittest.TestCase):
    """requirements.txt 同时声明微信检测器、zxing-cpp 和现有 QReader。"""

    def test_declares_three_decoders(self) -> None:
        """保留 qreader、rapidocr、onnxruntime，并追加两个不带版本号的新依赖。"""
        text = (ROOT / "requirements.txt").read_text()
        names = [line.strip() for line in text.splitlines() if line.strip()]
        self.assertIn("qreader", names)
        self.assertIn("opencv-contrib-python", names)
        self.assertIn("zxing-cpp", names)
        self.assertIn("rapidocr", names)
        self.assertIn("onnxruntime", names)
