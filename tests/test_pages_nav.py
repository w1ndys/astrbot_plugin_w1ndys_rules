# 页面层：Pages 顶栏和 antd CDN 约定。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
FOLDERS = ("settings", "keywords", "forbidden-test", "forbidden-logs")
SHARED = (
    "nav.js",
    "app.js",
    "settings-view.js",
    "keywords-view.js",
    "forbidden-test-view.js",
    "forbidden-logs-view.js",
)


class PagesNavTest(unittest.TestCase):
    def test_html_uses_antd_bundle(self) -> None:
        """不带 bundle 时图标会向站点根路径要 colors.blue，页面空白。"""
        for folder in FOLDERS:
            html = (PAGES / folder / "index.html").read_text()
            self.assertIn("antd@5.24.0?bundle&external=react,react-dom", html)

    def test_apps_mount_inpage_tabs(self) -> None:
        """四页都要能点 Tab 换面板。脚本只能引用本页目录。不改宿主 hash。"""
        for folder in FOLDERS:
            nav = (PAGES / folder / "nav.js").read_text()
            self.assertNotIn("window.top", nav)
            self.assertNotIn("#/plugin-page/", nav)
            self.assertIn("pageTabItems", nav)
            app = (PAGES / folder / "app.js").read_text()
            self.assertIn("pageTabItems", app)
            self.assertIn('type: "card"', app)
            self.assertIn("onChange: setActive", app)
            self.assertIn("./nav.js", app)
            self.assertNotIn("../nav.js", app)
            for name in SHARED:
                self.assertTrue((PAGES / folder / name).is_file(), name)
