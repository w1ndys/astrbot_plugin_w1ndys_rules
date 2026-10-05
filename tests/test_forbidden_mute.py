# 违禁禁言标记：命中记下这一对，管理员解开这次禁言才加本群白名单。
# 机器人自己解禁、没有标记的解禁都不加白。

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

from astrbot_plugin_w1ndys_rules.business.forbidden_action import apply_hit_actions
from astrbot_plugin_w1ndys_rules.business.verify_handle import PASS_REPLY
from astrbot_plugin_w1ndys_rules.business.whitelist import (
    pardon_forbidden_mute,
    should_skip_forbidden,
)
from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.data.forbidden_mute_store import ForbiddenMuteStore
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.data.whitelist_store import WhitelistStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    BLACKLIST_GLOBAL_SCOPE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_REASON_MODEL,
)
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


class FakeMessage:
    def __init__(self, raw, message_id=88) -> None:
        self.raw_message = raw
        self.message_id = message_id


class FakeEvent:
    """群通知事件：raw 里带 notice 字段，用来判断谁解禁。"""

    def __init__(
        self,
        raw=None,
        group_id: str = "123",
        user_id: str = "10001",
        operator_id: str = "10086",
    ) -> None:
        self.message_obj = FakeMessage(
            raw
            or {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": operator_id,
            }
        )
        self.group_id = group_id
        self.user_id = user_id
        self.stopped = False
        self.bot = FakeBot()

    def get_group_id(self) -> str:
        return self.group_id

    def get_sender_id(self) -> str:
        return self.user_id

    def get_self_id(self) -> str:
        return "999"

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


async def collect(agen) -> list:
    items = []
    async for item in agen:
        items.append(item)
    return items


class MuteStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = ForbiddenMuteStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_false(self) -> None:
        self.assertFalse(self.store.has("123", "10001"))

    async def test_mark_then_clear(self) -> None:
        await self.store.mark("123", "10001")
        self.assertTrue(self.store.has("123", "10001"))
        # 别的群没有这一对
        self.assertFalse(self.store.has("456", "10001"))
        cleared = await self.store.clear("123", "10001")
        self.assertTrue(cleared)
        self.assertFalse(self.store.has("123", "10001"))

    async def test_clear_missing_is_false(self) -> None:
        cleared = await self.store.clear("123", "10001")
        self.assertFalse(cleared)

    async def test_mark_twice_keeps_one_row(self) -> None:
        await self.store.mark("123", "10001")
        await self.store.mark("123", "10001")
        conn_calls = 1
        self.assertTrue(self.store.has("123", "10001"))
        self.assertEqual(conn_calls, 1)

    async def test_survives_reopen(self) -> None:
        await self.store.mark("123", "10001")
        reopened = ForbiddenMuteStore(self.db_path)
        self.assertTrue(reopened.has("123", "10001"))


class ApplyHitMuteTest(unittest.IsolatedAsyncioTestCase):
    """命中处置后按秒数记或清标记，不传存储时行为不变。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenMuteStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_mute_records_pair(self) -> None:
        event = FakeEvent()
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 60, FORBIDDEN_CFG_REMIND_TEXT: ""},
            "123",
            "广告",
            "这里有广告",
            None,
            None,
            FORBIDDEN_REASON_MODEL,
            "",
            mute_store=self.store,
        )
        self.assertTrue(self.store.has("123", "10001"))

    async def test_zero_seconds_clears_pair(self) -> None:
        """这次没禁言，旧标记不能留着，否则普通解禁会被当成加白。"""
        await self.store.mark("123", "10001")
        event = FakeEvent()
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0, FORBIDDEN_CFG_REMIND_TEXT: ""},
            "123",
            "广告",
            "这里有广告",
            None,
            None,
            FORBIDDEN_REASON_MODEL,
            "",
            mute_store=self.store,
        )
        self.assertFalse(self.store.has("123", "10001"))

    async def test_without_store_changes_nothing(self) -> None:
        """旧调用不传存储时不记标记，也不报错。"""
        event = FakeEvent()
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 60, FORBIDDEN_CFG_REMIND_TEXT: ""},
            "123",
            "广告",
            "这里有广告",
            None,
            None,
            FORBIDDEN_REASON_MODEL,
            "",
        )
        self.assertFalse(self.store.has("123", "10001"))


class PardonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.whitelist = WhitelistStore(db_path)
        self.blacklist = BlacklistStore(db_path)
        self.mutes = ForbiddenMuteStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _pardon(self) -> str:
        return await pardon_forbidden_mute(
            self.whitelist, self.blacklist, self.mutes, "123", "10001"
        )

    async def test_without_mark_is_silent(self) -> None:
        notice = await self._pardon()
        self.assertEqual(notice, "")
        self.assertFalse(self.whitelist.is_in("123", "10001"))

    async def test_mark_adds_one_group_only(self) -> None:
        await self.mutes.mark("123", "10001")
        notice = await self._pardon()
        self.assertEqual(notice, "已将 10001 加入本群白名单。")
        self.assertTrue(self.whitelist.is_in("123", "10001"))
        self.assertFalse(self.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        self.assertFalse(self.whitelist.is_in("456", "10001"))
        self.assertFalse(self.mutes.has("123", "10001"))

    async def test_group_blacklist_row_removed_global_kept(self) -> None:
        await self.mutes.mark("123", "10001")
        await self.blacklist.add("123", "10001")
        await self.blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        notice = await self._pardon()
        self.assertFalse(self.blacklist.is_in("123", "10001"))
        self.assertTrue(self.blacklist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        self.assertIn("不会跳过违禁", notice)

    async def test_global_blacklist_keeps_notice(self) -> None:
        await self.mutes.mark("123", "10001")
        await self.blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        notice = await self._pardon()
        self.assertTrue(self.whitelist.is_in("123", "10001"))
        self.assertTrue(self.blacklist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        self.assertIn("不会跳过违禁", notice)
        self.assertFalse(
            should_skip_forbidden(self.whitelist, self.blacklist, "123", "10001")
        )


class AdminUnmuteEntryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.context = None
        self.plugin.settings = {}
        self.plugin.verify = VerifyStore(db_path)
        self.plugin.whitelist = WhitelistStore(db_path)
        self.plugin.blacklist = BlacklistStore(db_path)
        self.plugin.forbidden_mutes = ForbiddenMuteStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_mark_adds_whitelist_and_notices(self) -> None:
        """没有 pending 也可能被违禁禁言，解禁后照样加白。"""
        await self.plugin.forbidden_mutes.mark("123", "10001")
        event = FakeEvent()
        sent = await collect(self.plugin.on_group_unmute(event))
        self.assertEqual(sent, ["已将 10001 加入本群白名单。"])
        self.assertTrue(self.plugin.whitelist.is_in("123", "10001"))
        self.assertFalse(
            self.plugin.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001")
        )
        # 别的群不该出现这一行
        self.assertFalse(self.plugin.whitelist.is_in("456", "10001"))
        self.assertFalse(self.plugin.forbidden_mutes.has("123", "10001"))

    async def test_pending_pass_and_whitelist_together(self) -> None:
        await self.plugin.verify.put("123", "10001", "123456")
        await self.plugin.forbidden_mutes.mark("123", "10001")
        event = FakeEvent()
        sent = await collect(self.plugin.on_group_unmute(event))
        # 先报验证通过，再加白通知
        self.assertEqual(sent, [PASS_REPLY, "已将 10001 加入本群白名单。"])
        self.assertEqual(self.plugin.verify.get_code("123", "10001"), "")

    async def test_without_mark_is_silent(self) -> None:
        event = FakeEvent()
        sent = await collect(self.plugin.on_group_unmute(event))
        self.assertEqual(sent, [])
        self.assertFalse(self.plugin.whitelist.is_in("123", "10001"))

    async def test_bot_unmute_keeps_mark(self) -> None:
        """机器人自己解禁不清标记，也不加白。"""
        await self.plugin.forbidden_mutes.mark("123", "10001")
        event = FakeEvent(operator_id="999")
        sent = await collect(self.plugin.on_group_unmute(event))
        self.assertEqual(sent, [])
        self.assertFalse(self.plugin.whitelist.is_in("123", "10001"))
        self.assertTrue(self.plugin.forbidden_mutes.has("123", "10001"))
