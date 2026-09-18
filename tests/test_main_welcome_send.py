# 入口层入群欢迎：只处理 group_increase 通知。

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
        """记录 @。"""

        def __init__(self, **kwargs) -> None:
            self.qq = kwargs.get("qq")

    class Node:
        """记录合并转发节点，避免覆盖其它入口测试的桩。"""

        def __init__(self, content, **kwargs) -> None:
            self.content = content
            self.uin = kwargs.get("uin")
            self.name = kwargs.get("name")

    class Plain:
        """记录纯文本。"""

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
from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_WELCOME_TEXT,
    FEATURE_INVITE,
    FEATURE_VERIFY,
    FEATURE_WELCOME,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw, group_id: str = "123", user_id: str = "10001") -> None:
        self.message_obj = FakeMessage(raw)
        self.group_id = group_id
        self.user_id = user_id
        self.stopped = False

    def get_group_id(self) -> str:
        return self.group_id

    def get_sender_id(self) -> str:
        return self.user_id

    def get_self_id(self) -> str:
        return "999"

    def stop_event(self) -> None:
        self.stopped = True

    def chain_result(self, chain):
        return chain

    def plain_result(self, text: str) -> str:
        return text


async def collect(agen) -> list:
    items = []
    async for item in agen:
        items.append(item)
    return items


class WelcomeSendEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.welcome = WelcomeStore(db_path)
        self.plugin.verify = VerifyStore(db_path)
        self.plugin.invite = InviteStore(db_path)
        self.plugin.switches = GroupSwitchStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_increase_sends_at_and_text(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_WELCOME, True)
        await self.plugin.welcome.set_content("123", "请先看群规")
        event = FakeEvent({"notice_type": "group_increase"})
        sent = await collect(self.plugin.on_group_increase(event))
        self.assertTrue(event.stopped)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0].qq, "10001")
        self.assertEqual(sent[0][1].text, "\n请先看群规")

    async def test_increase_off_is_silent(self) -> None:
        event = FakeEvent({"notice_type": "group_increase"})
        sent = await collect(self.plugin.on_group_increase(event))
        self.assertTrue(event.stopped)
        self.assertEqual(sent, [])

    async def test_plain_group_message_ignored(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_WELCOME, True)
        event = FakeEvent({"post_type": "message"})
        sent = await collect(self.plugin.on_group_increase(event))
        self.assertFalse(event.stopped)
        self.assertEqual(sent, [])

    async def test_increase_without_saved_text_uses_default(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_WELCOME, True)
        event = FakeEvent({"notice_type": "group_increase"})
        sent = await collect(self.plugin.on_group_increase(event))
        self.assertEqual(sent[0][1].text, "\n" + DEFAULT_WELCOME_TEXT)

    async def test_increase_verify_only_sends_code(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_VERIFY, True)
        event = FakeEvent({"notice_type": "group_increase"})
        sent = await collect(self.plugin.on_group_increase(event))
        code = self.plugin.verify.get_code("123", "10001")
        self.assertTrue(code)
        self.assertIn(code, sent[0][1].text)
        self.assertEqual(sent[0][0].qq, "10001")

    async def test_increase_welcome_and_verify_compose(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_WELCOME, True)
        await self.plugin.switches.set_on("123", FEATURE_VERIFY, True)
        await self.plugin.welcome.set_content("123", "请先看群规")
        event = FakeEvent({"notice_type": "group_increase"})
        sent = await collect(self.plugin.on_group_increase(event))
        code = self.plugin.verify.get_code("123", "10001")
        text = sent[0][1].text
        self.assertIn("请先看群规", text)
        self.assertIn(code, text)

    async def test_decrease_drops_pending_silently(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        event = FakeEvent({"notice_type": "group_decrease"})
        await self.plugin.on_group_decrease(event)
        self.assertTrue(event.stopped)
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")

    async def test_decrease_ignores_plain_message(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        event = FakeEvent({"post_type": "message"})
        await self.plugin.on_group_decrease(event)
        self.assertFalse(event.stopped)
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")

    async def test_admin_unmute_passes_pending(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        event = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": "10086",
            }
        )
        sent = await collect(self.plugin.on_group_unmute(event))
        self.assertTrue(event.stopped)
        self.assertEqual(sent, ["已通过人机验证。"])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")

    async def test_bot_unmute_does_not_pass(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        event = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": "999",
            }
        )
        sent = await collect(self.plugin.on_group_unmute(event))
        self.assertFalse(event.stopped)
        self.assertEqual(sent, [])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")

    async def test_increase_records_invite_edge(self) -> None:
        await self.plugin.switches.set_on("123", FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        await collect(self.plugin.on_group_increase(event))
        edge = self.plugin.invite.get_edge("123", "10001")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.inviter_id, "10086")
        self.assertEqual(edge.sub_type, "invite")
