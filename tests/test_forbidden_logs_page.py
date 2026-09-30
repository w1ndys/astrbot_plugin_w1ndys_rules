# 违禁日志页：必须等 AstrBot 注入 bridge 后再跑页面脚本。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "forbidden-logs"


class ForbiddenLogsPageAssetsTest(unittest.TestCase):
    """验证日志页脚本加载顺序和看图方式。"""

    def test_app_script_is_module(self) -> None:
        html = (PAGE / "index.html").read_text()
        self.assertIn('type="module" src="./app.js"', html)
        self.assertNotIn('<script src="./app.js">', html)
        self.assertIn("antd", html)
        self.assertIn('"react"', html)

    def test_images_shown_as_img_not_text(self) -> None:
        js = (PAGE / "app.js").read_text()
        self.assertIn("图片未能保存", js)
        self.assertIn("h(\"img\"", js)
        self.assertNotIn("<pre", js)
        self.assertNotIn("images", js)
