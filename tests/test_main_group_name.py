# 入口层群名 Pages：注册三个接口；拉取走记下的 OneBot，失败不写库。

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

from astrbot_plugin_w1ndys_rules.data.group_name_store import GroupNameStore
from astrbot_plugin_w1ndys_rules.entity.constants import PLUGIN_NAME
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeApi:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return self.result


class FakeBot:
    def __init__(self, result: object) -> None:
        self.api = FakeApi(result)


class FakeAdapter:
    """模仿 aiocqhttp：get_client 交出 CQHttp。"""

    def __init__(self, bot: object) -> None:
        self._bot = bot

    def get_client(self) -> object:
        """和官方适配器一样交客户端。"""
        return self._bot


class FakePlatforms:
    """context.platform_manager 只需要 insts 列表。"""

    def __init__(self, insts: list) -> None:
        self.platform_insts = insts


class FakeContext:
    def __init__(self) -> None:
        self.routes = []

    def register_web_api(self, path, handler, methods, desc) -> None:
        self.routes.append((path, handler, methods, desc))



class GroupNameEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.context = FakeContext()
        self.plugin.group_names = GroupNameStore(Path(self._tmp.name) / "rules.db")
        self.plugin._onebot = None

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_register_three_routes(self) -> None:
        self.plugin._register_group_name_pages()
        paths = [item[0] for item in self.plugin.context.routes]
        prefix = f"/{PLUGIN_NAME}/group-name/"
        self.assertEqual(
            paths,
            [prefix + "list", prefix + "pull", prefix + "save"],
        )

    async def test_pull_without_bot_fails(self) -> None:
        ok, message = await self.plugin._pull_group_names()
        self.assertFalse(ok)
        self.assertIn("OneBot", message)
        self.assertEqual(self.plugin.group_names.as_map(), {})

    async def test_pull_writes_nothing(self) -> None:
        bot = FakeBot([{"group_id": 1127665319, "group_name": "推荐群聊"}])
        self.plugin._onebot = bot
        ok, data = await self.plugin._pull_group_names()
        self.assertTrue(ok)
        self.assertEqual(
            data["items"],
            [{"group_id": "1127665319", "group_name": "推荐群聊"}],
        )
        self.assertEqual(bot.api.calls[0][0], "get_group_list")
        self.assertEqual(self.plugin.group_names.as_map(), {})

    async def test_pull_protocol_fail(self) -> None:
        bot = FakeBot(None)
        self.plugin._onebot = bot
        ok, message = await self.plugin._pull_group_names()
        self.assertFalse(ok)
        self.assertIn("失败", message)

    async def test_pull_from_adapter_without_event(self) -> None:
        bot = FakeBot([{"group_id": 1127665319, "group_name": "推荐群聊"}])
        self.plugin.context.platform_manager = FakePlatforms([FakeAdapter(bot)])
        ok, data = await self.plugin._pull_group_names()
        self.assertTrue(ok)
        self.assertEqual(
            data["items"],
            [{"group_id": "1127665319", "group_name": "推荐群聊"}],
        )
        self.assertIs(self.plugin._onebot, bot)
        self.assertEqual(self.plugin.group_names.as_map(), {})

    async def test_pull_skips_adapter_without_api(self) -> None:
        empty = type("P", (), {})()
        self.plugin.context.platform_manager = FakePlatforms([empty])
        ok, message = await self.plugin._pull_group_names()
        self.assertFalse(ok)
        self.assertIn("OneBot", message)

