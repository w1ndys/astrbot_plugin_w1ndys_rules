# 违禁词测试页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class ForbiddenTestPageTest(unittest.TestCase):
    """验证测试页脚本和三种试跑。"""

    def test_app_script_is_classic_defer(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('script defer src="./assets/index.js"', html)

    def test_kinds_are_in_app(self) -> None:
        """三种试跑都要能从页面选到。"""
        app = (SRC / "forbidden-test-view.jsx").read_text()
        self.assertIn('value: "text"', app)
        self.assertIn('value: "transcript"', app)
        self.assertIn('value: "qr"', app)
        self.assertIn("qr_found", app)
