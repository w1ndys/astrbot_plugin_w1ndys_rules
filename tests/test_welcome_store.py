# 欢迎语文案按群存取。没设过是 None，空串表示本群关闭。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore


class WelcomeStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = WelcomeStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_group_is_none(self) -> None:
        self.assertIsNone(self.store.get_content("123"))

    async def test_set_then_get(self) -> None:
        await self.store.set_content("123", "欢迎入群")
        self.assertEqual(self.store.get_content("123"), "欢迎入群")

    async def test_empty_string_is_stored(self) -> None:
        await self.store.set_content("123", "")
        self.assertEqual(self.store.get_content("123"), "")

    async def test_groups_are_isolated(self) -> None:
        await self.store.set_content("111", "甲群欢迎")
        await self.store.set_content("222", "乙群欢迎")
        self.assertEqual(self.store.get_content("111"), "甲群欢迎")
        self.assertEqual(self.store.get_content("222"), "乙群欢迎")

    async def test_overwrite_same_group(self) -> None:
        await self.store.set_content("123", "旧文案")
        await self.store.set_content("123", "新文案")
        self.assertEqual(self.store.get_content("123"), "新文案")

    async def test_survives_reopen(self) -> None:
        await self.store.set_content("123", "持久欢迎")
        reopened = WelcomeStore(self.db_path)
        self.assertEqual(reopened.get_content("123"), "持久欢迎")

    async def test_list_page_filters_and_pages(self) -> None:
        await self.store.set_content("111", "甲")
        await self.store.set_content("222", "乙")
        items, total = self.store.list_page("111", 0, 10)
        self.assertEqual(total, 1)
        self.assertEqual(items, [("111", "甲")])
        page, total = self.store.list_page("", 1, 1)
        self.assertEqual(total, 2)
        self.assertEqual(len(page), 1)

    async def test_delete_removes_row(self) -> None:
        await self.store.set_content("123", "欢迎")
        removed = await self.store.delete("123")
        self.assertTrue(removed)
        self.assertIsNone(self.store.get_content("123"))
        removed = await self.store.delete("123")
        self.assertFalse(removed)
