# 页面层：Pages 打成 IIFE 单文件。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "console"
SRC = ROOT / "dashboard" / "src"


class PagesNavTest(unittest.TestCase):
    def test_html_uses_iife_bundle(self) -> None:
        """普通 script defer 才会被 AstrBot 打上 asset_token。不要 ESM 拆文件。"""
        html = (PAGE / "index.html").read_text()
        self.assertNotIn("esm.sh", html)
        self.assertNotIn("importmap", html)
        self.assertIn('script defer src="./assets/index.js"', html)
        self.assertNotIn('type="module" src="./app.js"', html)
        self.assertTrue((PAGE / "assets" / "index.js").is_file())

    def test_single_console_route(self) -> None:
        """宿主只扫 pages/<页名>/index.html。现在只要 console。"""
        names = sorted(p.name for p in (ROOT / "pages").iterdir() if p.is_dir())
        self.assertEqual(names, ["console"])

    def test_source_has_inpage_tabs(self) -> None:
        """点 Tab 换面板，不改宿主 hash。"""
        nav = (SRC / "nav.js").read_text()
        self.assertNotIn("window.top", nav)
        self.assertNotIn("#/plugin-page/", nav)
        self.assertIn("forbidden-triggers", nav)
        self.assertIn("welcome", nav)
        app = (SRC / "App.jsx").read_text()
        self.assertIn('type="card"', app)
        self.assertIn("onChange={setActive}", app)
        self.assertIn("WelcomeView", app)
        self.assertIn("ForbiddenTriggersView", app)
