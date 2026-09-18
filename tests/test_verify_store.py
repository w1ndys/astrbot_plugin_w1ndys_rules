# 待验证表：没行不是 pending，写入能读到，群与人隔离，再入群覆盖，删行后消失。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore


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
