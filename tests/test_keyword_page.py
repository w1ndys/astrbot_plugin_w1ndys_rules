# WebUI 关键词表：分页、按群号过滤、保存和删除。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.keyword_page import (
    list_keywords,
    remove_keyword,
    save_keyword,
)
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore


class FakeContext:
    """给校验读唤醒前缀。"""

    def get_config(self) -> dict:
        return {"wake_prefix": ["/"]}


class KeywordPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KeywordStore(Path(self._tmp.name) / "rules.db")
        self.context = FakeContext()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_list_filters_by_group_and_pages(self) -> None:
        await self.store.upsert("111", "甲", "A")
        await self.store.upsert("222", "乙", "B")
        await self.store.upsert("111", "丙", "C")
        data = list_keywords(self.store, {"group_id": "111", "page": 1, "page_size": 1})
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["group_id"], "111")

    async def test_save_and_remove(self) -> None:
        ok, message = await save_keyword(
            self.context,
            self.store,
            {"group_id": "123", "keyword": "原神", "reply": "好玩"},
        )
        self.assertTrue(ok)
        self.assertIn("原神", message)
        self.assertEqual(self.store.find_reply("123", "原神"), "好玩")
        ok, message = await remove_keyword(
            self.store, {"group_id": "123", "keyword": "原神"}
        )
        self.assertTrue(ok)
        self.assertEqual(self.store.find_reply("123", "原神"), "")

    async def test_save_rejects_empty_group(self) -> None:
        ok, message = await save_keyword(
            self.context,
            self.store,
            {"group_id": "", "keyword": "原神", "reply": "好玩"},
        )
        self.assertFalse(ok)
        self.assertIn("群号", message)
