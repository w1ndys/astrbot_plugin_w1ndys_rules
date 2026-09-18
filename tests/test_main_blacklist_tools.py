# 入口层黑名单 Agent 工具：只取当前群号并调用已测试的业务层。不踢人。

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

    class Node:
        """记录合并转发节点，不发到 QQ。"""

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
    components.Node = Node
    components.Plain = Plain
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.message_components"] = components


install_astrbot_stubs()

from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    BLACKLIST_LIST_LIMIT,
    PLUGIN_NAME,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeEvent:
    """提供当前群号、管理员身份，并记下发出的合并转发。"""

    def __init__(self, group_id: str = "123", admin: bool = True) -> None:
        self.group_id = group_id
        self.admin = admin
        self.sent = []

    def get_group_id(self) -> str:
        return self.group_id

    def is_admin(self) -> bool:
        return self.admin

    def get_self_id(self) -> str:
        return "999"

    def chain_result(self, chain):
        return chain

    async def send(self, result) -> None:
        self.sent.append(result)


class BlacklistToolEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.blacklist = BlacklistStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_group_tools_add_list_delete(self) -> None:
        added = await self.plugin.tool_blacklist_add(self.event, "10001")
        listed = await self.plugin.tool_blacklist_list(self.event)
        deleted = await self.plugin.tool_blacklist_delete(self.event, "10001")
        self.assertEqual(added, "已加入本群黑名单：10001")
        self.assertIn("10001", listed)
        self.assertEqual(deleted, "已从本群黑名单移除：10001")
        self.assertEqual(self.event.sent, [])

    async def test_global_does_not_write_group_list(self) -> None:
        added = await self.plugin.tool_global_blacklist_add(self.event, "10001")
        group_listed = await self.plugin.tool_blacklist_list(self.event)
        global_listed = await self.plugin.tool_global_blacklist_list(self.event)
        self.assertEqual(added, "已加入全局黑名单：10001")
        self.assertEqual(group_listed, "本群黑名单是空的。")
        self.assertIn("10001", global_listed)

    async def test_private_chat_cannot_use(self) -> None:
        message = await self.plugin.tool_blacklist_add(FakeEvent(group_id=""), "10001")
        self.assertEqual(message, "这个功能只能在群里用。")

    async def test_overflow_sends_forward(self) -> None:
        for index in range(BLACKLIST_LIST_LIMIT + 1):
            await self.plugin.tool_blacklist_add(self.event, str(10000 + index))
        listed = await self.plugin.tool_blacklist_list(self.event)
        self.assertEqual(
            listed,
            f"已用合并消息发出本群黑名单，共 {BLACKLIST_LIST_LIMIT + 1} 人。",
        )
        self.assertEqual(len(self.event.sent), 1)
        node = self.event.sent[0][0]
        self.assertEqual(node.uin, "999")
        self.assertEqual(node.name, PLUGIN_NAME)
        self.assertIn("10000", node.content[0].text)
        self.assertIn(str(10000 + BLACKLIST_LIST_LIMIT), node.content[0].text)

    async def test_global_delete_keeps_group_entry(self) -> None:
        await self.plugin.tool_blacklist_add(self.event, "10001")
        await self.plugin.tool_global_blacklist_add(self.event, "10001")
        deleted = await self.plugin.tool_global_blacklist_delete(self.event, "10001")
        listed = await self.plugin.tool_blacklist_list(self.event)
        self.assertEqual(deleted, "已从全局黑名单移除：10001")
        self.assertIn("10001", listed)
