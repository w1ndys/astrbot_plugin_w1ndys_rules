# 全局配置页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class SettingsPageAssetsTest(unittest.TestCase):
    """验证配置页不展示密钥。"""

    def test_app_script_is_classic_defer(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('script defer src="./assets/index.js"', html)

    def test_no_webhook_field(self) -> None:
        for path in SRC.glob("*"):
            if path.suffix in {".js", ".jsx"}:
                js = path.read_text()
                self.assertNotIn("forbidden_feishu_webhook", js, path.name)
