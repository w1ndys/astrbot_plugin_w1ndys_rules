# 入口层邀请树查询工具：只取当前群号并调用业务层。

import sys
import tempfile
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

from astrbot_plugin_w1ndys_rules.business.invite_query import REJECT_MESSAGE
from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeEvent:
    """提供当前群号和管理员身份。"""

    def __init__(self, group_id: str = "123", admin: bool = True) -> None:
        self.group_id = group_id
        self.admin = admin

    def get_group_id(self) -> str:
        return self.group_id

    def is_admin(self) -> bool:
        return self.admin


class InviteToolEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.invite = InviteStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_upline_and_downline_tools(self) -> None:
        await self.plugin.invite.record("123", "10001", "10086", "invite")
        await self.plugin.invite.record("123", "10002", "10086", "invite")
        up = await self.plugin.tool_invite_upline(self.event, "10001")
        self.assertIn("10001 ← 10086", up)
        down = await self.plugin.tool_invite_downline(self.event, "10086")
        self.assertIn("下线（2 人）", down)
        self.assertIn("10001", down)
        self.assertIn("10002", down)

    async def test_non_admin_is_rejected(self) -> None:
        guest = FakeEvent(admin=False)
        self.assertEqual(
            await self.plugin.tool_invite_upline(guest, "10001"),
            REJECT_MESSAGE,
        )

    async def test_private_chat_is_rejected(self) -> None:
        private = FakeEvent(group_id="")
        text = await self.plugin.tool_invite_upline(private, "10001")
        self.assertIn("群", text)
