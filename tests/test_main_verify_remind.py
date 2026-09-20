# 入口层提醒循环：记下 OneBot，扫到期 pending；没 bot 不发。热重载要取消任务。

import asyncio
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

from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        # 发群消息要带回 message_id，后面撤回靠它
        if action == "send_group_msg":
            return {"message_id": 88}
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeEvent:
    """只提供 bot，给记住 OneBot 用。"""

    def __init__(self) -> None:
        self.bot = FakeBot()


class VerifyRemindEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.verify = VerifyStore(Path(self._tmp.name) / "rules.db")
        self.plugin._onebot = None
        self.plugin._remind_task = None

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_tick_without_bot_does_not_send(self) -> None:
        await self.plugin.verify.put("123", "10001", "111111")
        await self.plugin.verify.update_remind("123", "10001", "111111", 10, 0)
        await self.plugin._tick_reminds(20)
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "111111")

    async def test_tick_sends_due_and_skips_future(self) -> None:
        await self.plugin.verify.put("123", "10001", "111111")
        await self.plugin.verify.update_remind("123", "10001", "111111", 10, 0)
        await self.plugin.verify.set_prompt_message_id("123", "10001", "77")
        await self.plugin.verify.put("123", "10002", "222222")
        bot = FakeBot()
        self.plugin._onebot = bot
        await self.plugin._tick_reminds(20)
        self.assertNotEqual(self.plugin.verify.get_code("123", "10001"), "111111")
        self.assertEqual(self.plugin.verify.get_code("123", "10002"), "222222")
        self.assertEqual(bot.api.calls[0][0], "send_group_msg")
        self.assertEqual(bot.api.calls[1], ("delete_msg", {"message_id": 77}))

    def test_remember_bot_keeps_onebot(self) -> None:
        event = FakeEvent()
        self.plugin._remember_bot(event)
        self.assertIs(self.plugin._onebot, event.bot)
        empty = type("E", (), {})()
        self.plugin._remember_bot(empty)
        self.assertIs(self.plugin._onebot, event.bot)

    async def test_terminate_cancels_loop(self) -> None:
        self.plugin._start_remind_loop()
        task = self.plugin._remind_task
        self.assertIsNotNone(task)
        await self.plugin.terminate()
        self.assertTrue(task.done())
