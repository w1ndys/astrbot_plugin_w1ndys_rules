# 入口层入群验证 Agent 工具：只取当前群号并调用已测试的业务层。不踢人。

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

from astrbot_plugin_w1ndys_rules.business.verify_admin import REJECT_MESSAGE
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
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


class FakeEvent:
    """提供当前群号、管理员身份，并记下 @ 和禁言。"""

    def __init__(self, group_id: str = "123", admin: bool = True) -> None:
        self.group_id = group_id
        self.admin = admin
        self.sent = []
        self.bot = FakeBot()

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


class VerifyToolEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.verify = VerifyStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_pass_unmutes_recalls_and_mentions(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        await self.plugin.verify.set_prompt_message_id("123", "10001", "77")
        message = await self.plugin.tool_verify_pass(self.event, "10001")
        self.assertEqual(message, "已通过入群验证：10001")
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")
        self.assertEqual(self.event.bot.api.calls[0][0], "set_group_ban")
        self.assertEqual(
            self.event.bot.api.calls[0][1],
            {"group_id": 123, "user_id": 10001, "duration": 0},
        )
        self.assertEqual(self.event.bot.api.calls[1], ("delete_msg", {"message_id": 77}))
        self.assertEqual(self.event.bot.api.calls[2][0], "send_group_msg")
        payload = self.event.bot.api.calls[2][1]["message"]
        self.assertEqual(payload[0], {"type": "at", "data": {"qq": "10001"}})
        self.assertIn("已通过人机验证。", payload[1]["data"]["text"])

    async def test_reject_recalls_without_unmute(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        await self.plugin.verify.set_prompt_message_id("123", "10001", "77")
        message = await self.plugin.tool_verify_reject(self.event, "10001")
        self.assertEqual(message, "已拒绝入群验证：10001（未踢出）")
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")
        self.assertEqual(
            self.event.bot.api.calls,
            [("delete_msg", {"message_id": 77})],
        )

    async def test_scan_mentions_this_group_only(self) -> None:
        await self.plugin.verify.put("123", "10002", "222222")
        await self.plugin.verify.put("123", "10001", "111111")
        await self.plugin.verify.put("999", "10003", "333333")
        message = await self.plugin.tool_verify_scan(self.event)
        self.assertIn("10001", message)
        self.assertIn("10002", message)
        self.assertNotIn("10003", message)
        chain = self.event.sent[0]
        qqs = [item.qq for item in chain if hasattr(item, "qq")]
        self.assertEqual(qqs, ["10001", "10002"])

    async def test_private_chat_cannot_use(self) -> None:
        message = await self.plugin.tool_verify_pass(FakeEvent(group_id=""), "10001")
        self.assertEqual(message, "这个功能只能在群里用。")

    async def test_non_admin_is_rejected(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        guest = FakeEvent(admin=False)
        passed = await self.plugin.tool_verify_pass(guest, "10001")
        rejected = await self.plugin.tool_verify_reject(guest, "10001")
        scanned = await self.plugin.tool_verify_scan(guest)
        self.assertEqual(passed, REJECT_MESSAGE)
        self.assertEqual(rejected, REJECT_MESSAGE)
        self.assertEqual(scanned, REJECT_MESSAGE)
        self.assertEqual(guest.sent, [])
        self.assertEqual(guest.bot.api.calls, [])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "123456")
