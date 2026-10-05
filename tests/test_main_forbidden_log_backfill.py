# 入口层违禁日志回补：注册接口；逐群拉成员资料；某群失败不碰其他群的待补清单。

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
    web = types.ModuleType("astrbot.api.web")

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

        def exception(self, *_args, **_kwargs) -> None:
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

    def json_response(payload):
        """把成功响应收成一个对象，测试只看内容。"""
        return FakeResponse(payload, 200)

    def error_response(message, status_code: int = 400):
        """把错误响应收成一个对象，测试只看状态码和文案。"""
        return FakeResponse({"error": str(message)}, status_code)

    event.AstrMessageEvent = object
    event.filter = IdentityFilter()
    star.Context = object
    star.Star = Star
    star.StarTools = StarTools
    api.logger = Logger()
    components.At = At
    components.Node = Node
    components.Plain = Plain
    web.json_response = json_response
    web.error_response = error_response
    api.web = web
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.message_components"] = components
    sys.modules["astrbot.api.web"] = web


class FakeResponse:
    """WebUI 响应替身。payload 是响应体，status_code 是 HTTP 状态。"""

    def __init__(self, payload: object, status_code: int) -> None:
        self.payload = payload
        self.status_code = status_code


install_astrbot_stubs()

from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_REASON_MODEL,
    PLUGIN_NAME,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeApi:
    """按群号给成员资料；没有这一群就当作协议失败。"""

    def __init__(self, members: dict) -> None:
        self.members = members
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return self.members.get(kwargs.get("group_id"))


class FakeBot:
    def __init__(self, members: dict) -> None:
        self.api = FakeApi(members)


class FakeContext:
    def __init__(self) -> None:
        self.routes = []

    def register_web_api(self, path, handler, methods, desc) -> None:
        self.routes.append((path, handler, methods, desc))


class BackfillEntryTest(unittest.IsolatedAsyncioTestCase):
    """回补接口的注册、无 bot、逐群失败隔离。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.context = FakeContext()
        self.plugin.forbidden_logs = ForbiddenLogStore(
            Path(self._tmp.name) / "rules.db"
        )
        self.plugin._onebot = None

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_register_backfill_route(self) -> None:
        """入口把回补地址注册进页面路由。"""
        self.plugin._register_log_pages()
        paths = [item[0] for item in self.plugin.context.routes]
        self.assertIn(
            f"/{PLUGIN_NAME}/forbidden-log/backfill-nicknames", paths
        )

    async def test_no_pending_groups_returns_zero(self) -> None:
        """没有空昵称日志时直接返回 0，不用碰 OneBot。"""
        response = await self.plugin.page_forbidden_log_backfill()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["updated"], 0)
        self.assertEqual(response.payload["failed"], [])

    async def test_without_onebot_fails(self) -> None:
        """没有 OneBot 整次失败，已有日志不改。"""
        await self._insert_empty_name("111", "1")
        response = await self.plugin.page_forbidden_log_backfill()
        self.assertEqual(response.status_code, 400)
        self.assertIn("OneBot", response.payload["error"])
        self.assertEqual(self.plugin.forbidden_logs.get(1).sender_name, "")

    async def test_failed_group_keeps_its_own_logs_empty(self) -> None:
        """一群拉失败时只记这一群，另一群照补。"""
        await self._insert_empty_name("111", "1")
        await self._insert_empty_name("222", "2")
        self.plugin._onebot = FakeBot(
            {111: {"data": [{"user_id": 1, "card": "小明", "nickname": ""}]}}
        )
        response = await self.plugin.page_forbidden_log_backfill()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["updated"], 1)
        self.assertEqual(self.plugin.forbidden_logs.get(1).sender_name, "小明")
        self.assertEqual(self.plugin.forbidden_logs.get(2).sender_name, "")
        self.assertEqual(response.payload["failed"][0]["group_id"], "222")
        self.assertIn("222", response.payload["message"])

    async def _insert_empty_name(self, group_id: str, user_id: str) -> None:
        """写一条还没有群昵称的日志。"""
        await self.plugin.forbidden_logs.insert(
            group_id, user_id, FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
