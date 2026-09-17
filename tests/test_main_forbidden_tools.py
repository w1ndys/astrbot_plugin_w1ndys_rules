# 入口层违禁 Agent 工具：只取当前群号并调用已测试的业务层。

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


install_astrbot_stubs()

from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeEvent:
    """提供当前群号和管理员身份。"""

    def __init__(self, group_id: str = "123", admin: bool = True) -> None:
        """保存测试群号和权限。"""
        self.group_id = group_id
        self.admin = admin

    def get_group_id(self) -> str:
        """返回当前会话群号。"""
        return self.group_id

    def is_admin(self) -> bool:
        """返回管理员状态。"""
        return self.admin


class ForbiddenToolEntryTest(unittest.IsolatedAsyncioTestCase):
    """验证四个 Agent 工具都使用当前群号操作 SQLite。"""

    def setUp(self) -> None:
        """绕过 AstrBot 初始化，只注入真实临时存储。"""
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.forbidden = ForbiddenStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        """删除临时数据库。"""
        self._tmp.cleanup()

    async def test_tools_complete_crud_in_current_group(self) -> None:
        """新增、查询、修改、删除形成完整工具闭环。"""
        added = await self.plugin.tool_forbidden_add(self.event, "触发词", "广告")
        listed = await self.plugin.tool_forbidden_list(self.event)
        updated = await self.plugin.tool_forbidden_update(
            self.event, "触发词", "广告", "推广"
        )
        deleted = await self.plugin.tool_forbidden_delete(self.event, "触发词", "推广")

        self.assertEqual(added, "已添加违禁触发词「广告」。")
        self.assertIn("「广告」", listed)
        self.assertEqual(updated, "已将违禁触发词「广告」修改为「推广」。")
        self.assertEqual(deleted, "已删除违禁触发词「推广」。")

    async def test_private_chat_cannot_select_group(self) -> None:
        """没有当前群号时不能让模型通过参数指定别的群。"""
        message = await self.plugin.tool_forbidden_add(
            FakeEvent(group_id=""), "触发词", "广告"
        )

        self.assertEqual(message, "这个功能只能在群里用。")
