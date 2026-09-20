# 提醒间隔固定 2 小时。夜里不发；到期才换码。

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_remind import (
    in_remind_hours,
    remind_wait_minutes,
    rotate_due_code,
    send_due_remind,
)
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    VERIFY_REMIND_INTERVAL_MINUTES,
)

_BEIJING = ZoneInfo("Asia/Shanghai")


def _beijing_ts(hour: int, minute: int = 0) -> int:
    """固定一天的北京时间，方便测白天/夜里。"""
    return int(
        datetime(2026, 9, 20, hour, minute, tzinfo=_BEIJING).timestamp()
    )


class VerifyRemindTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VerifyStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wait_is_two_hours(self) -> None:
        self.assertEqual(remind_wait_minutes(), 120)

    def test_hours_only_beijing_daytime(self) -> None:
        self.assertFalse(in_remind_hours(_beijing_ts(7, 59)))
        self.assertTrue(in_remind_hours(_beijing_ts(8, 0)))
        self.assertTrue(in_remind_hours(_beijing_ts(21, 59)))
        self.assertFalse(in_remind_hours(_beijing_ts(22, 0)))
        self.assertFalse(in_remind_hours(_beijing_ts(23, 0)))

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
            now + VERIFY_REMIND_INTERVAL_MINUTES * 60,
        )

    async def test_second_rotate_still_two_hours(self) -> None:
        await self.store.put("123", "10001", "111111")
        first_due = self.store.get_next_remind_at("123", "10001")
        await rotate_due_code(self.store, "123", "10001", first_due)
        second_due = self.store.get_next_remind_at("123", "10001")
        await rotate_due_code(self.store, "123", "10001", second_due)
        self.assertEqual(self.store.get_remind_count("123", "10001"), 2)
        self.assertEqual(
            self.store.get_next_remind_at("123", "10001"),
            second_due + VERIFY_REMIND_INTERVAL_MINUTES * 60,
        )

    async def test_send_due_skips_when_not_due(self) -> None:
        await self.store.put("123", "10001", "111111")
        event = FakeSpeakEvent()
        next_at = self.store.get_next_remind_at("123", "10001")
        code = await send_due_remind(
            self.store, event, "123", "10001", next_at - 1
        )
        self.assertEqual(code, "")
        self.assertEqual(event.bot.api.calls, [])
        self.assertEqual(self.store.get_code("123", "10001"), "111111")

    async def test_send_due_skips_at_night(self) -> None:
        await self.store.put("123", "10001", "111111")
        night = _beijing_ts(23, 0)
        await self.store.update_remind("123", "10001", "111111", night, 0)
        event = FakeSpeakEvent()
        code = await send_due_remind(self.store, event, "123", "10001", night)
        self.assertEqual(code, "")
        self.assertEqual(event.bot.api.calls, [])
        self.assertEqual(self.store.get_code("123", "10001"), "111111")
        self.assertEqual(self.store.get_remind_count("123", "10001"), 0)

    async def test_send_due_sends_then_recalls_old(self) -> None:
        await self.store.put("123", "10001", "111111")
        day = _beijing_ts(10, 0)
        await self.store.update_remind("123", "10001", "111111", day, 0)
        await self.store.set_prompt_message_id("123", "10001", "77")
        event = FakeSpeakEvent()
        code = await send_due_remind(self.store, event, "123", "10001", day)
        self.assertTrue(code)
        self.assertNotEqual(code, "111111")
        self.assertEqual(self.store.get_prompt_message_id("123", "10001"), "88")
        self.assertEqual(event.bot.api.calls[0][0], "send_group_msg")
        payload = event.bot.api.calls[0][1]["message"]
        self.assertEqual(payload[0], {"type": "at", "data": {"qq": "10001"}})
        self.assertIn(code, payload[1]["data"]["text"])
        self.assertEqual(event.bot.api.calls[1], ("delete_msg", {"message_id": 77}))


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        # 发群消息要带回 message_id，后面撤回靠它
        if action == "send_group_msg":
            return {"message_id": 88}
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeSpeakEvent:
    """给发提醒/撤回提供 OneBot 调用记录。"""

    def __init__(self) -> None:
        self.bot = FakeBot()

    def get_self_id(self) -> str:
        return "999"
