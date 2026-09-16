# 群消息违禁路径：开关、触发词、是/否、处置。不打真实飞书。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_action import (
    feishu_text_payload,
    mute_seconds,
)
from astrbot_plugin_w1ndys_rules.business.forbidden_handle import (
    handle_forbidden_message,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_FORBIDDEN_MUTE_SECONDS,
    FEATURE_FORBIDDEN,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_CFG_TRIGGER_WORDS,
    MAX_FORBIDDEN_MUTE_SECONDS,
)


class FakeSwitches:
    def __init__(self, on: bool = True) -> None:
        self.on = on

    def is_on(self, group_id: str, feature: str) -> bool:
        # 测的是违禁词开关，别的功能键当关
        if feature != FEATURE_FORBIDDEN:
            return False
        return self.on


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeMessage:
    def __init__(self, message_id) -> None:
        self.message_id = message_id


class FakeEvent:
    def __init__(self, sender: str = "10001", self_id: str = "999", mid=123) -> None:
        self.bot = FakeBot()
        self._sender = sender
        self._self_id = self_id
        self.message_obj = FakeMessage(mid)

    def get_sender_id(self) -> str:
        return self._sender

    def get_self_id(self) -> str:
        return self._self_id


class FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        return FakeReply(self.text)


class FakeReply:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text
        self.role = "assistant"


def ready_config(**extra) -> dict:
    data = {
        FORBIDDEN_CFG_TRIGGER_WORDS: "广告",
        FORBIDDEN_CFG_SAMPLES: "卖课 -> 是",
        FORBIDDEN_CFG_GUIDELINE: "广告算违禁。",
        FORBIDDEN_CFG_MUTE_SECONDS: 60,
        FORBIDDEN_CFG_REMIND_TEXT: "请不要发广告。",
        FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://example.com/hook",
    }
    data.update(extra)
    return data


class MuteSecondsTest(unittest.TestCase):
    def test_default_and_clip(self) -> None:
        self.assertEqual(mute_seconds({}), DEFAULT_FORBIDDEN_MUTE_SECONDS)
        self.assertEqual(mute_seconds({FORBIDDEN_CFG_MUTE_SECONDS: 90}), 90)
        self.assertEqual(mute_seconds({FORBIDDEN_CFG_MUTE_SECONDS: 0}), 0)
        self.assertEqual(mute_seconds({FORBIDDEN_CFG_MUTE_SECONDS: -3}), 0)
        self.assertEqual(
            mute_seconds({FORBIDDEN_CFG_MUTE_SECONDS: 99999999}),
            MAX_FORBIDDEN_MUTE_SECONDS,
        )
        self.assertEqual(
            mute_seconds({FORBIDDEN_CFG_MUTE_SECONDS: "abc"}),
            DEFAULT_FORBIDDEN_MUTE_SECONDS,
        )

    def test_feishu_payload_is_text(self) -> None:
        body = feishu_text_payload("hello")
        self.assertEqual(body["msg_type"], "text")
        self.assertEqual(body["content"]["text"], "hello")


class ForbiddenHandleTest(unittest.IsolatedAsyncioTestCase):
    async def test_switch_off_skips(self) -> None:
        event = FakeEvent()
        handled, reply = await handle_forbidden_message(
            ready_config(),
            FakeSwitches(False),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(event.bot.api.calls, [])

    async def test_no_trigger_skips(self) -> None:
        event = FakeEvent()
        handled, reply = await handle_forbidden_message(
            ready_config(),
            FakeSwitches(True),
            event,
            "123",
            "今天天气不错",
            self._provider("是"),
        )
        self.assertFalse(handled)
        self.assertEqual(event.bot.api.calls, [])

    async def test_model_no_skips(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeSwitches(True),
            event,
            "123",
            "这里有广告",
            self._provider("否"),
        )
        self.assertFalse(handled)
        self.assertEqual(event.bot.api.calls, [])

    async def test_model_fail_skips(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeSwitches(True),
            event,
            "123",
            "这里有广告",
            self._provider("是的"),
        )
        self.assertFalse(handled)
        self.assertEqual(event.bot.api.calls, [])

    async def test_yes_recalls_mutes_reminds_and_feishu(self) -> None:
        event = FakeEvent()
        posted: list[tuple[str, dict]] = []

        def poster(url: str, body: dict) -> None:
            posted.append((url, body))

        handled, reply = await handle_forbidden_message(
            ready_config(),
            FakeSwitches(True),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            poster,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "请不要发广告。")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "set_group_ban"])
        self.assertEqual(event.bot.api.calls[0][1]["message_id"], 123)
        self.assertEqual(event.bot.api.calls[1][1]["duration"], 60)
        self.assertEqual(event.bot.api.calls[1][1]["user_id"], 10001)
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0][0], "https://example.com/hook")
        self.assertIn("广告", posted[0][1]["content"]["text"])
        self.assertNotIn("example.com", posted[0][1]["content"]["text"])

    async def test_empty_remind_and_no_https_webhook(self) -> None:
        event = FakeEvent()
        posted: list = []

        def poster(url: str, body: dict) -> None:
            posted.append((url, body))

        handled, reply = await handle_forbidden_message(
            ready_config(
                **{
                    FORBIDDEN_CFG_REMIND_TEXT: "",
                    FORBIDDEN_CFG_FEISHU_WEBHOOK: "http://example.com/hook",
                    FORBIDDEN_CFG_MUTE_SECONDS: 0,
                }
            ),
            FakeSwitches(True),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            poster,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg"])
        self.assertEqual(posted, [])

    async def test_skip_mute_self(self) -> None:
        event = FakeEvent(sender="999", self_id="999")
        handled, _reply = await handle_forbidden_message(
            ready_config(**{FORBIDDEN_CFG_FEISHU_WEBHOOK: ""}),
            FakeSwitches(True),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
        )
        self.assertTrue(handled)
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg"])

    def _provider(self, text: str):
        async def get_provider():
            return FakeProvider(text)

        return get_provider
