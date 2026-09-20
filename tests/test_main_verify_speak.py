# 入口层：群消息不再交码；私聊交码；违禁仍在群消息里先走，避免广告漏撤。

import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def install_astrbot_stubs() -> None:
    """安装最小 AstrBot 模块，让单元测试可以导入插件入口。"""
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")
    components = types.ModuleType("astrbot.api.message_components")

    class IdentityFilter:
        """把 AstrBot 装饰器替换成不改变函数的测试装饰器。"""

        class EventMessageType:
            GROUP_MESSAGE = "group"
            PRIVATE_MESSAGE = "private"

        def event_message_type(self, _message_type):
            """返回原函数。"""
            return lambda function: function

        def llm_tool(self, **_kwargs):
            """返回原函数。"""
            return lambda function: function

    class Star:
        """测试用插件基类。"""

    class StarTools:
        """测试不会调用真实数据目录。"""

        @staticmethod
        def get_data_dir() -> str:
            """返回当前目录作为兜底。"""
            return "."

    class Logger:
        """忽略入口层日志。"""

        def info(self, *_args, **_kwargs) -> None:
            """测试不输出日志。"""
            return

    class At:
        def __init__(self, **kwargs) -> None:
            self.qq = kwargs.get("qq")

    class Node:
        def __init__(self, content, **kwargs) -> None:
            self.content = content
            self.uin = kwargs.get("uin")
            self.name = kwargs.get("name")

    class Plain:
        def __init__(self, text, **_kwargs) -> None:
            self.text = text

    event.AstrMessageEvent = object
    event.filter = IdentityFilter()
    star.Context = object
    star.Star = Star
    star.StarTools = StarTools
    api.logger = Logger()
    components.At = At
    components.Node = Node
    components.Plain = Plain
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.message_components"] = components


install_astrbot_stubs()

from astrbot_plugin_w1ndys_rules._shared.group_switch_store import GroupSwitchStore
from astrbot_plugin_w1ndys_rules.business.verify_handle import FAIL_REPLY, PASS_REPLY
from astrbot_plugin_w1ndys_rules.data.activity_store import ActivityStore
from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FEATURE_FORBIDDEN,
    FEATURE_VERIFY,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_GLOBAL_SCOPE,
    FORBIDDEN_KIND_TRIGGER,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


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
    """给撤回取 message_id。没有 ID 时违禁路径会跳过撤回。"""

    def __init__(self, message_id=None) -> None:
        self.message_id = message_id


class FakeReply:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text
        self.role = "assistant"


class FakeProvider:
    """测试用对话提供商。固定回「是」或「否」。"""

    def __init__(self, text: str) -> None:
        self.text = text

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        return FakeReply(self.text)


class FakeEvent:
    def __init__(self, text: str, group_id: str = "123", user_id: str = "10001") -> None:
        self.message_str = text
        self.group_id = group_id
        self.user_id = user_id
        self.stopped = False
        self.bot = FakeBot()
        self.message_obj = FakeMessage(88)

    def get_group_id(self) -> str:
        return self.group_id

    def get_sender_id(self) -> str:
        return self.user_id

    def get_self_id(self) -> str:
        return "999"

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


async def collect(agen) -> list:
    items = []
    async for item in agen:
        items.append(item)
    return items


class VerifySpeakEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.context = None
        self.plugin.config = {}
        self.plugin.keywords = KeywordStore(db_path)
        self.plugin.welcome = WelcomeStore(db_path)
        self.plugin.verify = VerifyStore(db_path)
        self.plugin.forbidden = ForbiddenStore(db_path)
        self.plugin.activity = ActivityStore(db_path)
        self.plugin.switches = GroupSwitchStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _pending(self, code: str = "123456") -> None:
        await self.plugin.switches.set_on("123", FEATURE_VERIFY, True)
        await self.plugin.verify.put("123", "10001", code)

    async def test_group_text_does_not_verify(self) -> None:
        await self._pending()
        event = FakeEvent("hello")
        sent = await collect(self.plugin.on_group_message(event))
        self.assertEqual(sent, [])
        self.assertEqual(event.bot.api.calls, [])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")

    async def test_group_code_does_not_pass(self) -> None:
        await self._pending()
        event = FakeEvent("123456")
        sent = await collect(self.plugin.on_group_message(event))
        self.assertEqual(sent, [])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")

    async def test_private_fail_replies_and_stops(self) -> None:
        await self._pending()
        event = FakeEvent("hello")
        sent = await collect(self.plugin.on_private_verify(event))
        self.assertEqual(sent, [FAIL_REPLY])
        self.assertTrue(event.stopped)
        self.assertEqual(event.bot.api.calls, [])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")

    async def test_private_pass_unmutes_and_replies_privately(self) -> None:
        await self._pending()
        await self.plugin.verify.set_prompt_message_id("123", "10001", "77")
        event = FakeEvent("123456")
        sent = await collect(self.plugin.on_private_verify(event))
        self.assertEqual(sent, [PASS_REPLY])
        self.assertTrue(event.stopped)
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")
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

    async def test_pending_ad_is_recalled_before_verify_fail(self) -> None:
        await self._pending()
        await self.plugin.switches.set_on("123", FEATURE_FORBIDDEN, True)
        await self.plugin.forbidden.add(
            FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, "勤工俭学服务中心"
        )
        self.plugin.config = {
            FORBIDDEN_CFG_GUIDELINE: "广告算违禁。",
            FORBIDDEN_CFG_SAMPLES: "卖课 -> 是",
            FORBIDDEN_CFG_MUTE_SECONDS: 60,
            FORBIDDEN_CFG_REMIND_TEXT: "请不要发广告。",
        }

        async def get_provider():
            return FakeProvider("是")

        self.plugin._using_provider = get_provider
        event = FakeEvent("勤工俭学服务中心加群")
        sent = await collect(self.plugin.on_group_message(event))
        actions = [name for name, _kwargs in event.bot.api.calls]
        self.assertIn("delete_msg", actions)
        self.assertEqual(sent, ["请不要发广告。"])
        self.assertNotIn(FAIL_REPLY, sent)
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")
