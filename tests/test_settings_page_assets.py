# 全局配置页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "settings"


class SettingsPageAssetsTest(unittest.TestCase):
    """验证配置页不展示密钥。"""

    def test_app_script_is_module(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('type="module" src="./app.js"', html)
        self.assertNotIn('<script src="./app.js">', html)
        self.assertIn("antd", html)

    def test_no_webhook_field(self) -> None:
        js = (PAGE / "app.js").read_text()
        self.assertNotIn("forbidden_feishu_webhook", js)
