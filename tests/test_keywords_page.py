# 关键词表页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "console"


class KeywordPageAssetsTest(unittest.TestCase):
    """验证产物是 IIFE，不靠 CDN。"""

    def test_app_script_is_classic_defer(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('script defer src="./assets/index.js"', html)
        self.assertNotIn('type="module" src="./app.js"', html)
