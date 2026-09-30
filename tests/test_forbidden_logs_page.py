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
        js = (SRC / "forbidden-logs-view.jsx").read_text()
        self.assertIn("图片未能保存", js)
        self.assertIn("<img", js)
        self.assertNotIn("images", js)
