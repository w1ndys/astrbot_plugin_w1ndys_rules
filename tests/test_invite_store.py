# 邀请边按群存取。没记过是 None，重复入群覆盖成最新邀请人。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore


class InviteStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = InviteStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_none(self) -> None:
        self.assertIsNone(self.store.get_edge("123", "10001"))

    async def test_record_then_get(self) -> None:
        await self.store.record("123", "10001", "10086", "invite")
        edge = self.store.get_edge("123", "10001")
        self.assertEqual(edge.inviter_id, "10086")
        self.assertEqual(edge.sub_type, "invite")

    async def test_sub_type_persisted(self) -> None:
        await self.store.record("123", "10001", "10086", "approve")
        edge = self.store.get_edge("123", "10001")
        self.assertEqual(edge.sub_type, "approve")

    async def test_groups_are_isolated(self) -> None:
        await self.store.record("111", "10001", "20001", "invite")
        await self.store.record("222", "10001", "30001", "invite")
        self.assertEqual(self.store.get_edge("111", "10001").inviter_id, "20001")
        self.assertEqual(self.store.get_edge("222", "10001").inviter_id, "30001")

    async def test_rejoin_overwrites(self) -> None:
        await self.store.record("123", "10001", "10086", "invite")
        await self.store.record("123", "10001", "20002", "invite")
        self.assertEqual(self.store.get_edge("123", "10001").inviter_id, "20002")

    async def test_survives_reopen(self) -> None:
        await self.store.record("123", "10001", "10086", "invite")
        reopened = InviteStore(self.db_path)
        self.assertEqual(reopened.get_edge("123", "10001").inviter_id, "10086")
