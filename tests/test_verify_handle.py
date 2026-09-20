# 私聊交码：对了删行、撤提示、解禁、私聊报通过；错了只回私聊；没 pending 跳过。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_handle import (
    FAIL_REPLY,
    PASS_REPLY,
    handle_verify_private,
    match_private_code,
)
from astrbot_plugin_w1ndys_rules.business.verify_join import hint_text
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore


class VerifyHandleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.store = VerifyStore(db_path)
        self.group_id = "123"
        self.user_id = "10001"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _pending(self, code: str = "123456", prompt: str = "77") -> None:
        await self.store.put(self.group_id, self.user_id, code)
        await self.store.set_prompt_message_id(self.group_id, self.user_id, prompt)

    async def test_not_pending_skips(self) -> None:
        action, group_id, prompt = match_private_code(
            self.store, self.user_id, "123456"
        )
        self.assertEqual(action, "")
        self.assertEqual(group_id, "")
        self.assertEqual(prompt, "")

    async def test_empty_text_skips(self) -> None:
        await self._pending()
        action, group_id, prompt = match_private_code(self.store, self.user_id, "")
        self.assertEqual(action, "")
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_correct_code_matches_group(self) -> None:
        await self._pending("123456", "77")
        action, group_id, prompt = match_private_code(
            self.store, self.user_id, "123456"
        )
        self.assertEqual(action, "pass")
        self.assertEqual(group_id, self.group_id)
        self.assertEqual(prompt, "77")

    async def test_copied_hint_matches(self) -> None:
        await self._pending("123456")
        action, group_id, _prompt = match_private_code(
            self.store, self.user_id, hint_text("123456")
        )
        self.assertEqual(action, "pass")
        self.assertEqual(group_id, self.group_id)

    async def test_wrong_code_fails_and_keeps_pending(self) -> None:
        await self._pending()
        action, group_id, prompt = match_private_code(
            self.store, self.user_id, "hello"
        )
        self.assertEqual(action, "fail")
        self.assertEqual(group_id, "")
        self.assertEqual(prompt, "")
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_embedded_number_fails(self) -> None:
        await self._pending("123456")
        action, _group_id, _prompt = match_private_code(
            self.store, self.user_id, "123456789"
        )
        self.assertEqual(action, "fail")

    async def test_matches_only_the_group_with_that_code(self) -> None:
        await self.store.put("111", self.user_id, "111111")
        await self.store.put("222", self.user_id, "222222")
        action, group_id, _prompt = match_private_code(
            self.store, self.user_id, "222222"
        )
        self.assertEqual(action, "pass")
        self.assertEqual(group_id, "222")

    async def test_private_pass_unmutes_recalls_and_replies_privately(self) -> None:
        await self._pending("123456", "77")
        event = FakeSpeakEvent()
        handled, reply = await handle_verify_private(
            self.store, event, self.user_id, "123456"
        )
        self.assertTrue(handled)
        self.assertEqual(reply, PASS_REPLY)
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "")
        self.assertEqual(
            event.bot.api.calls,
            [
                ("delete_msg", {"message_id": 77}),
                (
                    "set_group_ban",
                    {"group_id": 123, "user_id": 10001, "duration": 0},
                ),
            ],
        )

    async def test_private_fail_does_not_call_onebot(self) -> None:
        await self._pending()
        event = FakeSpeakEvent()
        handled, reply = await handle_verify_private(
            self.store, event, self.user_id, "hello"
        )
        self.assertTrue(handled)
        self.assertEqual(reply, FAIL_REPLY)
        self.assertEqual(event.bot.api.calls, [])
        self.assertEqual(self.store.get_code(self.group_id, self.user_id), "123456")

    async def test_private_skip_does_not_call_onebot(self) -> None:
        event = FakeSpeakEvent()
        handled, reply = await handle_verify_private(
            self.store, event, self.user_id, "hello"
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
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
    """给撤回/解禁/群提醒提供 OneBot 调用记录。"""

    def __init__(self) -> None:
        self.bot = FakeBot()

    def get_self_id(self) -> str:
        return "999"
