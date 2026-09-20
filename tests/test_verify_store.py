# 待验证表：没行不是 pending，写入能读到，群与人隔离，再入群覆盖，删行后消失。
# 入群会排第一次提醒；到期列表和换码调度只动 pending。

import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.entity.constants import VERIFY_REMIND_FIRST_MINUTES


class VerifyStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = VerifyStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_empty(self) -> None:
        self.assertEqual(self.store.get_code("123", "10001"), "")
        self.assertEqual(self.store.list_user_ids("123"), [])
        self.assertFalse(self.store.code_in_use("123", "123456"))

    async def test_put_then_get(self) -> None:
        await self.store.put("123", "10001", "123456")
        self.assertEqual(self.store.get_code("123", "10001"), "123456")
        self.assertTrue(self.store.code_in_use("123", "123456"))
        self.assertEqual(self.store.list_user_ids("123"), ["10001"])

    async def test_groups_are_isolated(self) -> None:
        await self.store.put("111", "10001", "111111")
        self.assertEqual(self.store.get_code("111", "10001"), "111111")
        self.assertEqual(self.store.get_code("222", "10001"), "")
        self.assertTrue(self.store.code_in_use("111", "111111"))
        self.assertFalse(self.store.code_in_use("222", "111111"))

    async def test_users_are_isolated(self) -> None:
        await self.store.put("123", "10001", "123456")
        self.assertEqual(self.store.get_code("123", "10002"), "")
        self.assertEqual(self.store.list_user_ids("123"), ["10001"])

    async def test_rejoin_overwrites_code(self) -> None:
        await self.store.put("123", "10001", "111111")
        await self.store.put("123", "10001", "222222")
        self.assertEqual(self.store.get_code("123", "10001"), "222222")
        self.assertFalse(self.store.code_in_use("123", "111111"))
        self.assertTrue(self.store.code_in_use("123", "222222"))

    async def test_delete_clears_pending(self) -> None:
        await self.store.put("123", "10001", "123456")
        await self.store.delete("123", "10001")
        self.assertEqual(self.store.get_code("123", "10001"), "")
        self.assertFalse(self.store.code_in_use("123", "123456"))
        self.assertEqual(self.store.list_user_ids("123"), [])

    async def test_delete_missing_is_ok(self) -> None:
        await self.store.delete("123", "10001")
        self.assertEqual(self.store.get_code("123", "10001"), "")

    async def test_list_only_current_group(self) -> None:
        await self.store.put("111", "10002", "222222")
        await self.store.put("111", "10001", "111111")
        await self.store.put("222", "10003", "333333")
        self.assertEqual(self.store.list_user_ids("111"), ["10001", "10002"])
        self.assertEqual(self.store.list_user_ids("222"), ["10003"])

    async def test_survives_reopen(self) -> None:
        await self.store.put("123", "10001", "123456")
        reopened = VerifyStore(self.db_path)
        self.assertEqual(reopened.get_code("123", "10001"), "123456")
        self.assertTrue(reopened.code_in_use("123", "123456"))
        self.assertEqual(reopened.list_user_ids("123"), ["10001"])

    async def test_prompt_id_and_list_by_user(self) -> None:
        await self.store.put("123", "10001", "123456")
        await self.store.set_prompt_message_id("123", "10001", "77")
        await self.store.put("999", "10001", "654321")
        self.assertEqual(self.store.get_prompt_message_id("123", "10001"), "77")
        self.assertEqual(
            self.store.list_by_user("10001"),
            [("123", "123456", "77"), ("999", "654321", "")],
        )

    async def test_rejoin_clears_prompt_id(self) -> None:
        await self.store.put("123", "10001", "111111")
        await self.store.set_prompt_message_id("123", "10001", "77")
        await self.store.put("123", "10001", "222222")
        self.assertEqual(self.store.get_prompt_message_id("123", "10001"), "")

    async def test_prompt_survives_reopen(self) -> None:
        await self.store.put("123", "10001", "123456")
        await self.store.set_prompt_message_id("123", "10001", "77")
        reopened = VerifyStore(self.db_path)
        self.assertEqual(reopened.get_prompt_message_id("123", "10001"), "77")

    async def test_put_schedules_first_remind(self) -> None:
        before = int(time.time())
        await self.store.put("123", "10001", "123456")
        after = int(time.time())
        next_at = self.store.get_next_remind_at("123", "10001")
        wait = VERIFY_REMIND_FIRST_MINUTES * 60
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)
        self.assertGreaterEqual(next_at, before + wait)
        self.assertLessEqual(next_at, after + wait)
        self.assertEqual(self.store.list_due(before), [])
        self.assertEqual(self.store.list_due(next_at), [("123", "10001")])

    async def test_list_due_skips_future_and_other_group(self) -> None:
        await self.store.put("111", "10001", "111111")
        await self.store.put("222", "10002", "222222")
        await self.store.update_remind("111", "10001", "111111", 10, 1)
        await self.store.update_remind("222", "10002", "222222", 9999999999, 1)
        self.assertEqual(self.store.list_due(20), [("111", "10001")])

    async def test_update_remind_rotates_code_and_clears_prompt(self) -> None:
        await self.store.put("123", "10001", "111111")
        await self.store.set_prompt_message_id("123", "10001", "77")
        await self.store.update_remind("123", "10001", "222222", 50, 1)
        self.assertEqual(self.store.get_code("123", "10001"), "222222")
        self.assertEqual(self.store.get_prompt_message_id("123", "10001"), "")
        self.assertEqual(self.store.get_next_remind_at("123", "10001"), 50)
        self.assertEqual(self.store.get_remind_count("123", "10001"), 1)
        self.assertFalse(self.store.code_in_use("123", "111111"))

    async def test_update_remind_missing_is_noop(self) -> None:
        await self.store.update_remind("123", "10001", "222222", 50, 1)
        self.assertEqual(self.store.get_code("123", "10001"), "")
        self.assertEqual(self.store.get_next_remind_at("123", "10001"), 0)
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)

    async def test_delete_clears_schedule(self) -> None:
        await self.store.put("123", "10001", "123456")
        await self.store.delete("123", "10001")
        self.assertEqual(self.store.get_next_remind_at("123", "10001"), 0)
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)
        self.assertEqual(self.store.list_due(int(time.time()) + 999999), [])

    async def test_rejoin_resets_schedule(self) -> None:
        await self.store.put("123", "10001", "111111")
        await self.store.update_remind("123", "10001", "111111", 10, 3)
        await self.store.put("123", "10001", "222222")
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)
        self.assertGreater(
            self.store.get_next_remind_at("123", "10001"),
            int(time.time()),
        )

    async def test_remind_survives_reopen(self) -> None:
        await self.store.put("123", "10001", "123456")
        await self.store.update_remind("123", "10001", "654321", 88, 2)
        reopened = VerifyStore(self.db_path)
        self.assertEqual(reopened.get_code("123", "10001"), "654321")
        self.assertEqual(reopened.get_next_remind_at("123", "10001"), 88)
        self.assertEqual(reopened.get_remind_count("123", "10001"), 2)

    def test_old_table_gets_remind_columns(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DROP TABLE verify_pending")
            conn.execute(
                "CREATE TABLE verify_pending ("
                "group_id TEXT NOT NULL, user_id TEXT NOT NULL, "
                "code TEXT NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY (group_id, user_id))"
            )
            conn.execute(
                "INSERT INTO verify_pending("
                "group_id, user_id, code, created_at"
                ") VALUES ('123', '10001', '123456', '2026-09-18 00:00:00')"
            )
            conn.commit()
        finally:
            conn.close()
        store = VerifyStore(self.db_path)
        self.assertEqual(store.get_code("123", "10001"), "123456")
        self.assertEqual(store.get_next_remind_at("123", "10001"), 0)
        self.assertEqual(store.get_remind_count("123", "10001"), 0)
        self.assertEqual(store.list_due(0), [("123", "10001")])
