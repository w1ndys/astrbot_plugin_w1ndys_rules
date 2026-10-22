# 邀请树页：源码约定和接口路径，避免页面打到 404。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
PAGE = ROOT / "pages" / "console"


class InvitePageAssetsTest(unittest.TestCase):
    """验证页内 Tab、页面源码和后端注册的路径一致。"""

    def test_nav_has_invite_tab(self) -> None:
        nav = (SRC / "nav.ts").read_text()
        self.assertIn('key: "invite"', nav)
        self.assertIn('label: "邀请树"', nav)

    def test_app_renders_invite_view(self) -> None:
        app = (SRC / "App.tsx").read_text()
        self.assertIn("InviteView", app)
        self.assertIn('tab.key === "invite"', app)

    def test_view_calls_invite_apis(self) -> None:
        view = (SRC / "invite-view.tsx").read_text()
        self.assertIn("invite/tree", view)
        self.assertIn("invite/list", view)
        self.assertIn("输入 QQ 号", view)
        self.assertIn("本人", view)

    def test_main_registers_invite_paths(self) -> None:
        source = (ROOT / "main.py").read_text()
        self.assertIn("invite/tree", source)
        self.assertIn("invite/list", source)

    def test_bundle_exists(self) -> None:
        self.assertTrue((PAGE / "assets" / "index.js").is_file())
