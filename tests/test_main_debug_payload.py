# 入口层 debug 工具：只在群里把查看原始 payload 交给业务层。

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
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

    event.AstrMessageEvent = object
    event.filter = IdentityFilter()
    star.Context = object
    star.Star = Star
    star.StarTools = StarTools
    api.logger = Logger()
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.message_components"] = components


install_astrbot_stubs()

from astrbot_plugin_w1ndys_rules.business.debug_payload import (
    NO_MATCH,
    REJECT_MESSAGE,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeApi:
    def __init__(self) -> None:
        self.sent = []

    async def call_action(self, action: str, **kwargs):
        # 私聊发出去就记下来
        if action == "send_private_msg":
            self.sent.append(kwargs)
            return {}
        if action == "get_msg":
            return {"message_id": kwargs.get("message_id"), "message": []}
        if action == "get_group_msg_history":
            return {
                "messages": [
                    {"message_id": 11, "time": 1, "message": []},
                    {"message_id": 100, "time": 2, "message": []},
                ]
            }
        return None


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeEvent:
    """提供当前群号、管理员身份和 OneBot 桩。"""

    def __init__(self, group_id: str = "123", admin: bool = True) -> None:
        self.group_id = group_id
        self.admin = admin
        self.bot = FakeBot()

    def get_group_id(self) -> str:
        return self.group_id

    def get_sender_id(self) -> str:
        return "10086"

    def is_admin(self) -> bool:
        return self.admin

    def get_message_id(self) -> str:
        return "100"


class DebugPayloadEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = RulesPlugin.__new__(RulesPlugin)

    async def test_admin_can_inspect_in_group(self) -> None:
        event = FakeEvent()
        text = await self.plugin.tool_inspect_message_payload(event, "11")
        self.assertIn("已私聊发给你", text)
        self.assertEqual(len(event.bot.api.sent), 1)

    async def test_non_admin_rejected(self) -> None:
        event = FakeEvent(admin=False)
        text = await self.plugin.tool_inspect_message_payload(event, "11")
        self.assertEqual(text, REJECT_MESSAGE)

    async def test_private_chat_cannot_use(self) -> None:
        event = FakeEvent(group_id="")
        text = await self.plugin.tool_inspect_message_payload(event, "11")
        self.assertEqual(text, "这个功能只能在群里用。")

    async def test_missing_target_uses_previous(self) -> None:
        event = FakeEvent()
        text = await self.plugin.tool_inspect_message_payload(event, "")
        self.assertIn("已私聊发给你", text)

    async def test_empty_history_has_no_match(self) -> None:
        event = FakeEvent()

        async def empty_history(action: str, **kwargs):
            if action == "get_group_msg_history":
                return {"messages": []}
            if action == "send_private_msg":
                event.bot.api.sent.append(kwargs)
                return {}
            return None

        event.bot.api.call_action = empty_history
        text = await self.plugin.tool_inspect_message_payload(event, "")
        self.assertEqual(text, NO_MATCH)
