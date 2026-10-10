# 违禁日志页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class ForbiddenLogsPageAssetsTest(unittest.TestCase):
    """验证日志页脚本加载顺序和看图方式。"""

    def test_app_script_is_classic_defer(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('script defer src="./assets/index.js"', html)

    def test_images_shown_as_img_not_text(self) -> None:
        js = (SRC / "forbidden-logs-view.tsx").read_text()
        self.assertIn("图片未能保存", js)
        self.assertIn("<img", js)
        self.assertNotIn("images", js)


class ForbiddenLogsRosterSourceTest(unittest.TestCase):
    """源码约定：四个名单按钮、请求路径和行号参数。"""

    def test_roster_buttons_and_paths(self) -> None:
        js = (SRC / "forbidden-logs-view.tsx").read_text()
        self.assertIn("加入本群白名单", js)
        self.assertIn("加入全局白名单", js)
        self.assertIn("加入本群黑名单", js)
        self.assertIn("加入全局黑名单", js)
        self.assertIn("whitelist/add", js)
        self.assertIn("blacklist/add", js)
        self.assertIn("source_group_id", js)

    def test_main_registers_roster_paths(self) -> None:
        """入口注册的地址和页面写的一致，否则按钮会打到 404。"""
        source = (ROOT / "main.py").read_text()
        self.assertIn("/whitelist/add", source)
        self.assertIn("/whitelist/remove", source)
        self.assertIn("/blacklist/add", source)
        self.assertIn("/blacklist/remove", source)


class ForbiddenLogsNameSourceTest(unittest.TestCase):
    """源码约定：群名读共享映射，群昵称来自日志，回补走新接口。"""

    def test_view_reads_shared_group_name_map(self) -> None:
        js = (SRC / "forbidden-logs-view.tsx").read_text()
        self.assertIn("群名", js)
        self.assertIn("群昵称", js)
        self.assertIn("group-name/list", js)
        self.assertIn("forbidden-log/backfill-nicknames", js)
        # 日志页不另存群名，也不在这里拉群列表
        self.assertNotIn("group-name/save", js)
        self.assertNotIn("group-name/pull", js)

    def test_main_registers_backfill_path(self) -> None:
        """入口注册的回补地址和页面写的一致，否则按钮会打到 404。"""
        source = (ROOT / "main.py").read_text()
        self.assertIn("/forbidden-log/backfill-nicknames", source)
