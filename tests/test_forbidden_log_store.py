# 违禁日志数据层：插入、筛选分页、改原因不改原文、删除。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_REASON_GROUP_CARD,
    FORBIDDEN_REASON_MODEL,
)


class ForbiddenLogStoreTest(unittest.IsolatedAsyncioTestCase):
    """用真实临时 SQLite 验证日志表。"""

    def setUp(self) -> None:
        """每个测试独立库。"""
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenLogStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        """删临时库。"""
        self._tmp.cleanup()

    async def test_insert_reload_and_get(self) -> None:
        """写完重开还能按 id 拿到原文。"""
        log_id = await self.store.insert(
            "123",
            "10001",
            FORBIDDEN_REASON_MODEL,
            "文本模型命中：广告",
            "这里有广告",
            "[]",
            "[]",
        )
        reloaded = ForbiddenLogStore(Path(self._tmp.name) / "rules.db")
        row = reloaded.get(log_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.group_id, "123")
        self.assertEqual(row.user_id, "10001")
        self.assertEqual(row.reason_code, FORBIDDEN_REASON_MODEL)
        self.assertEqual(row.text, "这里有广告")
        self.assertEqual(row.json_text, "[]")
        self.assertEqual(row.images, "[]")
        self.assertTrue(row.created_at)

    async def test_list_filters_and_pages(self) -> None:
        """按群、人、原因筛，新的在前，能翻页。"""
        await self.store.insert(
            "111", "1", FORBIDDEN_REASON_MODEL, "a", "t1", "[]", "[]"
        )
        await self.store.insert(
            "222", "1", FORBIDDEN_REASON_GROUP_CARD, "b", "t2", "[]", "[]"
        )
        await self.store.insert(
            "111", "2", FORBIDDEN_REASON_MODEL, "c", "t3", "[]", "[]"
        )
        items, total = self.store.list_page("111", "", "", 0, 1)
        self.assertEqual(total, 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].text, "t3")
        items, total = self.store.list_page("", "1", FORBIDDEN_REASON_GROUP_CARD, 0, 10)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].group_id, "222")

    async def test_update_reason_keeps_originals(self) -> None:
        """改原因不能动原文三列。"""
        log_id = await self.store.insert(
            "123", "9", FORBIDDEN_REASON_MODEL, "旧", "原文", "[1]", "[2]"
        )
        ok = await self.store.update_reason(
            log_id, FORBIDDEN_REASON_GROUP_CARD, "群名片拦截"
        )
        self.assertTrue(ok)
        row = self.store.get(log_id)
        self.assertEqual(row.reason_code, FORBIDDEN_REASON_GROUP_CARD)
        self.assertEqual(row.reason_text, "群名片拦截")
        self.assertEqual(row.text, "原文")
        self.assertEqual(row.json_text, "[1]")
        self.assertEqual(row.images, "[2]")

    async def test_delete_missing(self) -> None:
        """没有这条删除返回 False。"""
        self.assertFalse(await self.store.delete(99))
        log_id = await self.store.insert(
            "1", "2", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        self.assertTrue(await self.store.delete(log_id))
        self.assertIsNone(self.store.get(log_id))
