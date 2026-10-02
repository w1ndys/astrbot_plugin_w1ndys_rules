# 欢迎语和关键词页只读群名映射，不调 OneBot 拉取。

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


class GroupNamePageAssetsTest(unittest.TestCase):
    """三页都有群名列；只有配置页能拉取和保存。"""

    def test_welcome_reads_map_only(self) -> None:
        js = (SRC / "welcome-view.jsx").read_text()
        self.assertIn("group-name/list", js)
        self.assertIn('title: "群名"', js)
        self.assertNotIn("group-name/pull", js)
        self.assertNotIn("group-name/save", js)

    def test_keywords_reads_map_only(self) -> None:
        js = (SRC / "keywords-view.jsx").read_text()
        self.assertIn("group-name/list", js)
        self.assertIn('title: "群名"', js)
        self.assertNotIn("group-name/pull", js)
        self.assertNotIn("group-name/save", js)
