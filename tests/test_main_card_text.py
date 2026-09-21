# 入口层：纯卡片没有 message_str 也要拦群名片；名单外的群不拦。

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

from astrbot_plugin_w1ndys_rules._shared.group_switch_store import GroupSwitchStore
from astrbot_plugin_w1ndys_rules.data.activity_store import ActivityStore
from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin

GROUP_CARD = {
    "prompt": "群名片: 卷心菜大军",
    "bizsrc": "qun.share",
    "meta": {"contact": {"tag": "群名片", "nickname": "卷心菜大军"}},
}


class Json:
    """AstrBot Json 组件替身。"""

    def __init__(self, data) -> None:
        self.data = data


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
    """给撤回取 message_id。"""

    def __init__(self, message_id=None) -> None:
        self.message_id = message_id
        self.raw_message = {"sender": {"role": ""}}


class FakeEvent:
    def __init__(
        self,
        text: str,
        group_id: str = "123",
        user_id: str = "10001",
        messages=None,
    ) -> None:
        self.message_str = text
        self.group_id = group_id
        self.user_id = user_id
        self.stopped = False
        self.bot = FakeBot()
        self.message_obj = FakeMessage(88)
        self._messages = messages or []

    def get_group_id(self) -> str:
        return self.group_id

    def get_sender_id(self) -> str:
        return self.user_id

    def get_self_id(self) -> str:
        return "999"

    def get_messages(self):
        return self._messages

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


async def collect(agen) -> list:
    items = []
    async for item in agen:
        items.append(item)
    return items


class GroupCardEntryTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_card_only_is_blocked(self) -> None:
        self.plugin.config = {
            FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS: ["123"],
            FORBIDDEN_CFG_MUTE_SECONDS: 60,
            FORBIDDEN_CFG_REMIND_TEXT: "不要发群名片。",
        }
        event = FakeEvent("", messages=[Json(GROUP_CARD)])
        sent = await collect(self.plugin.on_group_message(event))
        actions = [name for name, _kwargs in event.bot.api.calls]
        self.assertIn("delete_msg", actions)
        self.assertEqual(sent, ["不要发群名片。"])
        self.assertTrue(event.stopped)

    async def test_switch_off_skips_card(self) -> None:
        self.plugin.config = {FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS: []}
        event = FakeEvent("", messages=[Json(GROUP_CARD)])
        sent = await collect(self.plugin.on_group_message(event))
        self.assertEqual(sent, [])
        self.assertEqual(event.bot.api.calls, [])
        self.assertFalse(event.stopped)
