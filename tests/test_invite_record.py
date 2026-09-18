# 入群写邀请边：开关要开，邀请人要能读到，拿不到或自己邀自己不写。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules._shared.group_switch_store import GroupSwitchStore
from astrbot_plugin_w1ndys_rules.business.invite_record import record_join
from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore
from astrbot_plugin_w1ndys_rules.entity.constants import FEATURE_INVITE


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有消息对象时不是通知
        if has_obj:
            self.message_obj = FakeMessage(raw)
        else:
            self.message_obj = None


class InviteRecordTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.store = InviteStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        self.group_id = "123"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_switch_off_does_not_record(self) -> None:
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "10001", "999"
        )
        self.assertFalse(recorded)
        self.assertIsNone(self.store.get_edge(self.group_id, "10001"))

    async def test_invite_records_inviter(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "10001", "999"
        )
        self.assertTrue(recorded)
        edge = self.store.get_edge(self.group_id, "10001")
        self.assertEqual(edge.inviter_id, "10086")
        self.assertEqual(edge.sub_type, "invite")

    async def test_approve_records_operator(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "approve",
                "operator_id": "10086",
            }
        )
        await record_join(
            self.store, self.switches, event, self.group_id, "10001", "999"
        )
        self.assertEqual(
            self.store.get_edge(self.group_id, "10001").sub_type, "approve"
        )

    async def test_rejoin_overwrites_inviter(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        first = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        second = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "20002",
            }
        )
        await record_join(
            self.store, self.switches, first, self.group_id, "10001", "999"
        )
        await record_join(
            self.store, self.switches, second, self.group_id, "10001", "999"
        )
        self.assertEqual(
            self.store.get_edge(self.group_id, "10001").inviter_id, "20002"
        )

    async def test_missing_operator_is_skipped(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        zero = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "approve",
                "operator_id": "0",
            }
        )
        empty = FakeEvent({"notice_type": "group_increase", "sub_type": "invite"})
        self.assertFalse(
            await record_join(
                self.store, self.switches, zero, self.group_id, "10001", "999"
            )
        )
        self.assertFalse(
            await record_join(
                self.store, self.switches, empty, self.group_id, "10001", "999"
            )
        )
        self.assertIsNone(self.store.get_edge(self.group_id, "10001"))

    async def test_self_invite_is_skipped(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10001",
            }
        )
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "10001", "999"
        )
        self.assertFalse(recorded)
        self.assertIsNone(self.store.get_edge(self.group_id, "10001"))

    async def test_bot_self_join_is_skipped(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "999", "999"
        )
        self.assertFalse(recorded)
        self.assertIsNone(self.store.get_edge(self.group_id, "999"))

    async def test_missing_user_is_skipped(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent(
            {
                "notice_type": "group_increase",
                "sub_type": "invite",
                "operator_id": "10086",
            }
        )
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "", "999"
        )
        self.assertFalse(recorded)

    async def test_plain_message_has_no_edge(self) -> None:
        await self.switches.set_on(self.group_id, FEATURE_INVITE, True)
        event = FakeEvent({"post_type": "message"})
        recorded = await record_join(
            self.store, self.switches, event, self.group_id, "10001", "999"
        )
        self.assertFalse(recorded)
        self.assertIsNone(self.store.get_edge(self.group_id, "10001"))
