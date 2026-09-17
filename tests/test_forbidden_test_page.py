# 违禁词测试页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "forbidden-test"


class ForbiddenTestPageTest(unittest.TestCase):
    """验证测试页脚本加载顺序不会早于 bridge SDK。"""

    def test_app_script_is_module(self) -> None:
        """普通脚本会在 SDK 注入前执行，必须用 type=module。"""
        html = (PAGE / "index.html").read_text()

        self.assertIn('type="module" src="./app.js"', html)
        self.assertNotIn('<script src="./app.js">', html)
