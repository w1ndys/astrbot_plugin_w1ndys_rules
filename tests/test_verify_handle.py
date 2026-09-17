# 待验证发言：对了删行；错了给错码文案和禁言秒数；关开关、没文本、不是 pending 都跳过。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules._shared.group_switch_store import GroupSwitchStore
from astrbot_plugin_w1ndys_rules.business.verify_handle import (
    FAIL_REPLY,
    PASS_REPLY,
    handle_pending_speak,
    handle_verify_message,
)
from astrbot_plugin_w1ndys_rules.business.verify_join import hint_text
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_VERIFY_MUTE_SECONDS,
    FEATURE_VERIFY,
    VERIFY_CFG_MUTE_SECONDS,
)


class VerifyHandleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.store = VerifyStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        self.group_id = "123"
        self.user_id = "10001"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _pending(self, code: str = "123456") -> None:
        await self.switches.set_on(self.group_id, FEATURE_VERIFY, True)
        await self.store.put(self.group_id, self.user_id, code)

    async def test_not_pending_skips(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_VERIFY, True)
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            "123456",
        )
        self.assertEqual(action, "")
        self.assertEqual(reply, "")
        self.assertEqual(mute, 0)

    async def test_switch_off_skips_even_if_pending(self) -> None:
        await self.store.put(self.group_id, self.user_id, "123456")
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            "hello",
        )
        self.assertEqual(action, "")
        self.assertEqual(mute, 0)
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_empty_text_skips(self) -> None:
        await self._pending()
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            "",
        )
        self.assertEqual(action, "")
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_correct_code_passes_and_deletes(self) -> None:
        await self._pending("123456")
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            "123456",
        )
        self.assertEqual(action, "pass")
        self.assertEqual(reply, PASS_REPLY)
        self.assertEqual(mute, 0)
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "")

    async def test_copied_hint_passes(self) -> None:
        await self._pending("123456")
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            hint_text("123456"),
        )
        self.assertEqual(action, "pass")
        self.assertEqual(reply, PASS_REPLY)
        self.assertEqual(mute, 0)

    async def test_wrong_code_fails_and_keeps_pending(self) -> None:
        await self._pending("123456")
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {},
            self.group_id,
            self.user_id,
            "hello",
        )
        self.assertEqual(action, "fail")
        self.assertEqual(reply, FAIL_REPLY)
        self.assertEqual(mute, DEFAULT_VERIFY_MUTE_SECONDS)
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_embedded_number_fails(self) -> None:
        await self._pending("123456")
        action, reply, mute = await handle_pending_speak(
            self.store,
            self.switches,
            {VERIFY_CFG_MUTE_SECONDS: "60"},
            self.group_id,
            self.user_id,
            "123456789",
        )
        self.assertEqual(action, "fail")
        self.assertEqual(mute, 60)
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_verify_message_pass_unmutes(self) -> None:
        await self._pending("123456")
        event = FakeSpeakEvent()
        handled, reply, note = await handle_verify_message(
            self.store,
            self.switches,
            {},
            event,
            self.group_id,
            self.user_id,
            "123456",
        )
        self.assertTrue(handled)
        self.assertEqual(reply, PASS_REPLY)
        self.assertTrue(note)
        self.assertEqual(
            event.bot.api.calls,
            [
                (
                    "set_group_ban",
                    {"group_id": 123, "user_id": 10001, "duration": 0},
                )
            ],
        )

    async def test_verify_message_fail_mutes(self) -> None:
        await self._pending("123456")
        event = FakeSpeakEvent()
        handled, reply, note = await handle_verify_message(
            self.store,
            self.switches,
            {VERIFY_CFG_MUTE_SECONDS: "60"},
            event,
            self.group_id,
            self.user_id,
            "hello",
        )
        self.assertTrue(handled)
        self.assertEqual(reply, FAIL_REPLY)
        self.assertFalse(note)
        self.assertEqual(
            event.bot.api.calls,
            [
                (
                    "set_group_ban",
                    {"group_id": 123, "user_id": 10001, "duration": 60},
                )
            ],
        )

    async def test_verify_message_skip_does_not_call_onebot(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_VERIFY, True)
        event = FakeSpeakEvent()
        handled, reply, note = await handle_verify_message(
            self.store,
            self.switches,
            {},
            event,
            self.group_id,
            self.user_id,
            "hello",
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertFalse(note)
        self.assertEqual(event.bot.api.calls, [])


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeSpeakEvent:
    """给禁言/解禁提供 OneBot 调用记录。"""

    def __init__(self) -> None:
        self.bot = FakeBot()

    def get_self_id(self) -> str:
        return "999"
