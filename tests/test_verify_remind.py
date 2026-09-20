# 提醒间隔：0→2、之后翻倍封顶 30。到期才换码；没 pending 或没到点不动库。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_remind import (
    remind_wait_minutes,
    rotate_due_code,
)
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore


class VerifyRemindTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VerifyStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wait_doubles_then_caps(self) -> None:
        self.assertEqual(remind_wait_minutes(0), 2)
        self.assertEqual(remind_wait_minutes(1), 4)
        self.assertEqual(remind_wait_minutes(2), 8)
        self.assertEqual(remind_wait_minutes(3), 16)
        self.assertEqual(remind_wait_minutes(4), 30)
        self.assertEqual(remind_wait_minutes(5), 30)
        self.assertEqual(remind_wait_minutes(-1), 2)

    async def test_rotate_missing_is_empty(self) -> None:
        code = await rotate_due_code(self.store, "123", "10001", 100)
        self.assertEqual(code, "")
        self.assertEqual(self.store.get_code("123", "10001"), "")

    async def test_rotate_not_due_keeps_code(self) -> None:
        await self.store.put("123", "10001", "111111")
        next_at = self.store.get_next_remind_at("123", "10001")
        code = await rotate_due_code(self.store, "123", "10001", next_at - 1)
        self.assertEqual(code, "")
        self.assertEqual(self.store.get_code("123", "10001"), "111111")
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)

    async def test_rotate_due_replaces_code_and_schedules(self) -> None:
        await self.store.put("123", "10001", "111111")
        now = self.store.get_next_remind_at("123", "10001")
        code = await rotate_due_code(self.store, "123", "10001", now)
        self.assertTrue(code)
        self.assertNotEqual(code, "111111")
        self.assertEqual(self.store.get_code("123", "10001"), code)
        self.assertFalse(self.store.code_in_use("123", "111111"))
        self.assertEqual(self.store.get_remind_count("123", "10001"), 1)
        self.assertEqual(
            self.store.get_next_remind_at("123", "10001"),
            now + 4 * 60,
        )

    async def test_second_rotate_uses_eight_minutes(self) -> None:
        await self.store.put("123", "10001", "111111")
        first_due = self.store.get_next_remind_at("123", "10001")
        await rotate_due_code(self.store, "123", "10001", first_due)
        second_due = self.store.get_next_remind_at("123", "10001")
        await rotate_due_code(self.store, "123", "10001", second_due)
        self.assertEqual(self.store.get_remind_count("123", "10001"), 2)
        self.assertEqual(
            self.store.get_next_remind_at("123", "10001"),
            second_due + 8 * 60,
        )
