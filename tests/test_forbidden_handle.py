# 群消息违禁路径：开关、触发词、是/否、处置。不打真实飞书。

import sys
import tempfile
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
from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.data.whitelist_store import WhitelistStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    BLACKLIST_GLOBAL_SCOPE,
    CFG_FORBIDDEN_GROUPS,
    DEFAULT_FORBIDDEN_MUTE_SECONDS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_KIND_TRIGGER,
    FORBIDDEN_REASON_MODEL,
    MAX_FORBIDDEN_MUTE_SECONDS,
)


class FakeForbiddenStore:
    """给正式群消息路径提供全局触发词。"""

    def list_contents(self, group_id: str, kind: str) -> list[str]:
        """返回固定触发词。"""
        if kind == FORBIDDEN_KIND_TRIGGER:
            return ["广告"]
        return []


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
    def __init__(self, message_id, role: str = "") -> None:
        self.message_id = message_id
        self.raw_message = {"sender": {"role": role}}
        self.timestamp = 1759377600


class FakeEvent:
    def __init__(
        self, sender: str = "10001", self_id: str = "999", mid=123, role: str = ""
    ) -> None:
        self.bot = FakeBot()
        self._sender = sender
        self._self_id = self_id
        self.message_obj = FakeMessage(mid, role)

    def get_sender_id(self) -> str:
        return self._sender

    def get_self_id(self) -> str:
        return self._self_id


class FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        self.calls += 1
        return FakeReply(self.text)


class FakeReply:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text
        self.role = "assistant"


def ready_config(**extra) -> dict:
    data = {
        FORBIDDEN_CFG_GUIDELINE: "广告算违禁。",
        FORBIDDEN_CFG_SAMPLES: "卖课 -> 是",
        FORBIDDEN_CFG_MUTE_SECONDS: 60,
        FORBIDDEN_CFG_REMIND_TEXT: "请不要发广告。",
        FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://example.com/hook",
        CFG_FORBIDDEN_GROUPS: ["123"],
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
            ready_config(**{CFG_FORBIDDEN_GROUPS: []}),
            FakeForbiddenStore(),
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
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
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
            FakeForbiddenStore(),
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
            FakeForbiddenStore(),
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
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是\n像招嫖引流"),
            poster,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "请不要发广告。")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "get_group_msg_history", "set_group_ban"])
        self.assertEqual(event.bot.api.calls[0][1]["message_id"], 123)
        self.assertEqual(event.bot.api.calls[2][1]["duration"], 60)
        self.assertEqual(event.bot.api.calls[2][1]["user_id"], 10001)

        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0][0], "https://example.com/hook")
        feishu = posted[0][1]["content"]["text"]
        self.assertIn("广告", feishu)
        self.assertIn("时间：", feishu)
        self.assertIn("判定原因：像招嫖引流", feishu)
        self.assertNotIn("example.com", feishu)

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
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            poster,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "get_group_msg_history"])

        self.assertEqual(posted, [])

    async def test_skip_mute_self(self) -> None:
        event = FakeEvent(sender="999", self_id="999")
        handled, _reply = await handle_forbidden_message(
            ready_config(**{FORBIDDEN_CFG_FEISHU_WEBHOOK: ""}),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
        )
        self.assertTrue(handled)
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg"])

    async def test_owner_skips_without_model(self) -> None:
        event = FakeEvent(role="owner")
        provider = FakeProvider("是")

        async def get_provider():
            return provider

        handled, reply = await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            get_provider,
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(event.bot.api.calls, [])

    async def test_admin_skips_without_model(self) -> None:
        event = FakeEvent(role="admin")
        provider = FakeProvider("是")

        async def get_provider():
            return provider

        handled, reply = await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            get_provider,
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(event.bot.api.calls, [])

    async def test_member_still_detects(self) -> None:
        event = FakeEvent(role="member")
        handled, reply = await handle_forbidden_message(
            ready_config(**{FORBIDDEN_CFG_FEISHU_WEBHOOK: ""}),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "请不要发广告。")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "get_group_msg_history", "set_group_ban"])


    async def test_never_seen_still_detects(self) -> None:
        event = FakeEvent(role="member")
        handled, reply = await handle_forbidden_message(
            ready_config(**{FORBIDDEN_CFG_FEISHU_WEBHOOK: ""}),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "请不要发广告。")
        actions = [item[0] for item in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "get_group_msg_history", "set_group_ban"])


    async def test_yes_writes_log(self) -> None:
        """模型说「是」才落日志，text 存送审用户文本而不是外层 message_str。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        event = FakeEvent()
        event.message_str = "  这里有广告  "
        handled, _reply = await handle_forbidden_message(
            ready_config(**{FORBIDDEN_CFG_FEISHU_WEBHOOK: ""}),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            log_store=store,
        )
        self.assertTrue(handled)
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertEqual(total, 1)
        self.assertEqual(items[0].reason_code, FORBIDDEN_REASON_MODEL)
        # 日志文本是送审用户文本，不是外层 message_str
        self.assertEqual(items[0].text, "这里有广告")
        self.assertNotEqual(items[0].text, event.message_str)
        # 系统提示和样本不进日志
        self.assertNotIn("你是群规违禁判断器", items[0].text)
        self.assertEqual(items[0].user_id, "10001")

    async def test_skip_does_not_write_log(self) -> None:
        """没命中不写日志。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        event = FakeEvent()
        await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
            event,
            "123",
            "今天天气不错",
            self._provider("是"),
            log_store=store,
        )
        _items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertEqual(total, 0)

    async def test_whitelist_skips_this_group_only(self) -> None:
        """只在本群白名单：本群不送模型，别的群照常检测。"""
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "rules.db"
        whitelist = WhitelistStore(db_path)
        blacklist = BlacklistStore(db_path)
        await whitelist.add("123", "10001")
        provider = FakeProvider("是")

        async def get_provider():
            return provider

        config = ready_config(**{CFG_FORBIDDEN_GROUPS: ["123", "456"]})
        event = FakeEvent()
        handled, reply = await handle_forbidden_message(
            config,
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            get_provider,
            whitelist=whitelist,
            blacklist=blacklist,
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(event.bot.api.calls, [])

        other = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            config,
            FakeForbiddenStore(),
            other,
            "456",
            "这里有广告",
            get_provider,
            whitelist=whitelist,
            blacklist=blacklist,
        )
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(provider.calls, 1)
        self.assertIn("set_group_ban", [name for name, _kwargs in other.bot.api.calls])

    async def test_global_whitelist_skips_every_group(self) -> None:
        """global 行让两个群都跳过。"""
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "rules.db"
        whitelist = WhitelistStore(db_path)
        blacklist = BlacklistStore(db_path)
        await whitelist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        provider = FakeProvider("是")

        async def get_provider():
            return provider

        config = ready_config(**{CFG_FORBIDDEN_GROUPS: ["123", "456"]})
        for group_id in ("123", "456"):
            event = FakeEvent()
            handled, _reply = await handle_forbidden_message(
                config,
                FakeForbiddenStore(),
                event,
                group_id,
                "这里有广告",
                get_provider,
                whitelist=whitelist,
                blacklist=blacklist,
            )
            self.assertFalse(handled)
            self.assertEqual(event.bot.api.calls, [])
        tmp.cleanup()
        self.assertEqual(provider.calls, 0)

    async def test_blacklist_beats_whitelist(self) -> None:
        """本群或全局黑名单压过白名单，照样处置。"""
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "rules.db"
        whitelist = WhitelistStore(db_path)
        blacklist = BlacklistStore(db_path)
        await whitelist.add("123", "10001")
        await whitelist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        await blacklist.add("123", "10001")
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            whitelist=whitelist,
            blacklist=blacklist,
        )
        self.assertTrue(handled)

        other = FakeEvent()
        await blacklist.remove("123", "10001")
        await blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        handled, _reply = await handle_forbidden_message(
            ready_config(**{CFG_FORBIDDEN_GROUPS: ["123", "456"]}),
            FakeForbiddenStore(),
            other,
            "456",
            "这里有广告",
            self._provider("是"),
            whitelist=whitelist,
            blacklist=blacklist,
        )
        tmp.cleanup()
        self.assertTrue(handled)

    def _provider(self, text: str):
        async def get_provider():
            return FakeProvider(text)

        return get_provider

    async def test_feishu_message_equals_log_text(self) -> None:
        """模型命中时飞书「消息」正文和这条日志的文本是同一份送审文本。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        posted: list[tuple[str, dict]] = []

        def poster(url: str, body: dict) -> None:
            posted.append((url, body))

        event = FakeEvent()
        event.message_str = "  这里有广告  "
        await handle_forbidden_message(
            ready_config(),
            FakeForbiddenStore(),
            event,
            "123",
            "这里有广告",
            self._provider("是"),
            poster,
            log_store=store,
        )
        items, _total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        feishu = posted[0][1]["content"]["text"]
        self.assertIn(f"消息：{items[0].text}", feishu)
