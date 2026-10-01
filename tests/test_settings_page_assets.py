# 全局配置页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class SettingsPageAssetsTest(unittest.TestCase):
    """验证配置页在 Pages 改，官方 schema 全部隐藏。"""

    def test_app_script_is_classic_defer(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('script defer src="./assets/index.js"', html)

    def test_webhook_field_on_settings_page(self) -> None:
        js = (SRC / "settings-view.jsx").read_text()
        self.assertIn("forbidden_feishu_webhook", js)
        self.assertIn("Input.Password", js)

    def test_settings_view_groups_by_group(self) -> None:
        # 配置页按群号勾选，不再按功能用 tags 填群号。
        js = (SRC / "settings-view.jsx").read_text()
        self.assertIn("listsToRows", js)
        self.assertIn("rowsToLists", js)
        self.assertIn("按群号", js)
        self.assertNotIn('mode="tags"', js)
