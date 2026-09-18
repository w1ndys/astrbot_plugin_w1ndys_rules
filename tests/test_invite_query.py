# 邀请树查询：上线链、整条下线、权限和号码校验。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.invite_query import (
    REJECT_MESSAGE,
    show_downline,
    show_upline,
    walk_downline,
    walk_upline,
)
from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore
from astrbot_plugin_w1ndys_rules.entity.constants import INVITE_DOWNLINE_LIMIT


class FakeEvent:
    """测试用的发言人。只提供 is_admin。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        """当前发言人是不是管理员。"""
        return self._admin


class InviteQueryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = InviteStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent(admin=True)
        self.group_id = "123"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_upline_chain(self) -> None:
        await self.store.record(self.group_id, "10001", "10086", "invite")
        await self.store.record(self.group_id, "10086", "20002", "invite")
        chain = walk_upline(self.store, self.group_id, "10001")
        self.assertEqual(chain, ["10001", "10086", "20002"])
        text = show_upline(self.store, self.event, self.group_id, "10001")
        self.assertIn("10001 ← 10086 ← 20002", text)

    async def test_upline_missing(self) -> None:
        text = show_upline(self.store, self.event, self.group_id, "10001")
        self.assertEqual(text, "本群没有 10001 的邀请记录")

    async def test_upline_cycle_stops(self) -> None:
        await self.store.record(self.group_id, "10001", "10086", "invite")
        await self.store.record(self.group_id, "10086", "10001", "invite")
        chain = walk_upline(self.store, self.group_id, "10001")
        self.assertEqual(chain, ["10001", "10086"])

    async def test_downline_tree(self) -> None:
        await self.store.record(self.group_id, "10001", "10086", "invite")
        await self.store.record(self.group_id, "10002", "10086", "invite")
        await self.store.record(self.group_id, "10003", "10001", "invite")
        shown, total = walk_downline(self.store, self.group_id, "10086")
        self.assertEqual(total, 3)
        self.assertEqual(
            shown, [("10001", 1), ("10002", 1), ("10003", 2)]
        )
        text = show_downline(self.store, self.event, self.group_id, "10086")
        self.assertIn("下线（3 人）", text)
        self.assertIn("10001", text)
        self.assertIn("  10003", text)

    async def test_downline_empty(self) -> None:
        text = show_downline(self.store, self.event, self.group_id, "10086")
        self.assertEqual(text, "本群 10086 还没有下线")

    async def test_non_admin_rejected(self) -> None:
        guest = FakeEvent(admin=False)
        self.assertEqual(
            show_upline(self.store, guest, self.group_id, "10001"),
            REJECT_MESSAGE,
        )
        self.assertEqual(
            show_downline(self.store, guest, self.group_id, "10001"),
            REJECT_MESSAGE,
        )

    async def test_bad_user_id(self) -> None:
        self.assertEqual(
            show_upline(self.store, self.event, self.group_id, "张三"),
            "QQ 号必须是数字。",
        )

    async def test_downline_limit_reports_rest(self) -> None:
        for i in range(INVITE_DOWNLINE_LIMIT + 3):
            await self.store.record(
                self.group_id, str(20000 + i), "10086", "invite"
            )
        text = show_downline(self.store, self.event, self.group_id, "10086")
        self.assertIn(f"下线（{INVITE_DOWNLINE_LIMIT + 3} 人）", text)
        self.assertIn("其余 3 人未显示", text)
