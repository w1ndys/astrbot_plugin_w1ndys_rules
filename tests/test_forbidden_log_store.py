# 违禁日志数据层：插入、筛选分页、改原因不改原文、删除；旧库补群昵称列。

import sqlite3
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

# 本功能上线前的日志表结构：没有 sender_name 列，用来验证旧库补列
OLD_TABLE_SQL = """
CREATE TABLE forbidden_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    json TEXT NOT NULL,
    images TEXT NOT NULL
)
"""


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
        self.assertEqual(row.sender_name, "")
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

    def test_old_table_gains_sender_name_column(self) -> None:
        """旧库没有群昵称列时补列，旧行读出空串而不是报错。"""
        db_path = Path(self._tmp.name) / "old.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(OLD_TABLE_SQL)
            conn.execute(
                "INSERT INTO forbidden_log(group_id, user_id, reason_code, "
                "reason_text, created_at, text, json, images) "
                "VALUES ('1', '2', 'model', 'r', '2026-10-05 00:00:00', "
                "'旧正文', '[]', '[]')"
            )
            conn.commit()
        finally:
            conn.close()
        store = ForbiddenLogStore(db_path)
        row = store.get(1)
        self.assertIsNotNone(row)
        self.assertEqual(row.sender_name, "")
        self.assertEqual(row.text, "旧正文")

    async def test_insert_keeps_sender_name(self) -> None:
        """命中写入的群昵称能读回来，详情和列表都带这一列。"""
        log_id = await self.store.insert(
            "123",
            "10001",
            FORBIDDEN_REASON_MODEL,
            "文本模型命中",
            "正文",
            "[]",
            "[]",
            "小明",
        )
        row = self.store.get(log_id)
        self.assertEqual(row.sender_name, "小明")
        items, _total = self.store.list_page("123", "", "", 0, 10)
        self.assertEqual(items[0].sender_name, "小明")

    async def test_backfill_keeps_existing_sender_name(self) -> None:
        """回补只填空昵称：已写过的行不动，写入条数只算空行。"""
        await self.store.insert(
            "111", "1", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]", "旧名片"
        )
        await self.store.insert(
            "111", "2", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        await self.store.insert(
            "222", "3", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        self.assertEqual(self.store.groups_with_empty_sender_name(), ["111", "222"])
        written = await self.store.backfill_sender_names(
            "111", {"1": "新名片", "2": "小刚", "9": "查不到"}
        )
        self.assertEqual(written, 1)
        self.assertEqual(self.store.get(1).sender_name, "旧名片")
        self.assertEqual(self.store.get(2).sender_name, "小刚")
        # 111 补完了，只剩 222 还留着空昵称
        self.assertEqual(self.store.groups_with_empty_sender_name(), ["222"])

    async def test_backfill_out_of_group_member_stays_empty(self) -> None:
        """成员资料为空，或成员不在这一群时，空昵称保持空。"""
        await self.store.insert(
            "111", "2", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        self.assertEqual(await self.store.backfill_sender_names("111", {}), 0)
        self.assertEqual(self.store.get(1).sender_name, "")
        # 别的群的成员资料不能填到这一群的日志上
        self.assertEqual(await self.store.backfill_sender_names("222", {"2": "小刚"}), 0)
        self.assertEqual(self.store.get(1).sender_name, "")
