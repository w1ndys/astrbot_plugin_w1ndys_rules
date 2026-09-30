# 页面层：Pages 顶栏和本地 vendor 约定。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "console"
SHARED = (
    "nav.js",
    "app.js",
    "settings-view.js",
    "keywords-view.js",
    "forbidden-test-view.js",
    "forbidden-logs-view.js",
)
VENDOR = ("react.js", "react-dom.js", "client.js", "antd.js")


class PagesNavTest(unittest.TestCase):
    def test_html_uses_local_vendor(self) -> None:
        """依赖放本页 vendor，不走 esm.sh。"""
        html = (PAGE / "index.html").read_text()
        self.assertNotIn("esm.sh", html)
        self.assertNotIn("importmap", html)
        app = (PAGE / "app.js").read_text()
        self.assertIn("./vendor/antd.js", app)
        self.assertIn("./vendor/react.js", app)
        for name in VENDOR:
            self.assertTrue((PAGE / "vendor" / name).is_file(), name)

    def test_single_console_route(self) -> None:
        """宿主只扫 pages/<页名>/index.html。现在只要 console。"""
        names = sorted(p.name for p in (ROOT / "pages").iterdir() if p.is_dir())
        self.assertEqual(names, ["console"])

    def test_app_mounts_inpage_tabs(self) -> None:
        """点 Tab 换面板，不改宿主 hash。脚本只能引用本页目录。"""
        nav = (PAGE / "nav.js").read_text()
        self.assertNotIn("window.top", nav)
        self.assertNotIn("#/plugin-page/", nav)
        self.assertIn("pageTabItems", nav)
        app = (PAGE / "app.js").read_text()
        self.assertIn("pageTabItems", app)
        self.assertIn('type: "card"', app)
        self.assertIn("onChange: setActive", app)
        self.assertIn("./nav.js", app)
        self.assertNotIn("../nav.js", app)
        for name in SHARED:
            self.assertTrue((PAGE / name).is_file(), name)

    def test_vendor_imports_have_spaces(self) -> None:
        """压缩包 from\"./x\" 对不上 AstrBot 改写正则，请求会没 token 变成 401。"""
        for name in VENDOR:
            js = (PAGE / "vendor" / name).read_text()
            self.assertNotIn('from"./', js, name)
            self.assertNotIn('import"./', js, name)
