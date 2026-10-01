# 欢迎语 Pages 表：分页、按群号过滤、保存空串关闭、删除改回继承全局。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.welcome_page import (
    list_welcomes,
    remove_welcome,
    save_welcome,
)
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore


class WelcomePageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = WelcomeStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_list_filters_by_group_and_pages(self) -> None:
        await self.store.set_content("111", "甲群欢迎")
        await self.store.set_content("222", "乙群欢迎")
        data = list_welcomes(self.store, {"group_id": "111", "page": 1, "page_size": 1})
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["group_id"], "111")
        self.assertEqual(data["items"][0]["content"], "甲群欢迎")

    async def test_save_empty_closes_group(self) -> None:
        ok, message = await save_welcome(
            self.store, {"group_id": "123", "content": ""}
        )
        self.assertTrue(ok)
        self.assertIn("关闭", message)
        self.assertEqual(self.store.get_content("123"), "")

    async def test_save_rejects_empty_group(self) -> None:
        ok, message = await save_welcome(
            self.store, {"group_id": "", "content": "欢迎"}
        )
        self.assertFalse(ok)
        self.assertIn("群号", message)

    async def test_remove_restores_inherit(self) -> None:
        await self.store.set_content("123", "本群欢迎")
        ok, message = await remove_welcome(self.store, {"group_id": "123"})
        self.assertTrue(ok)
        self.assertIn("全局", message)
        self.assertIsNone(self.store.get_content("123"))
