# 黑名单按群存，全局用固定 group_id。群与群互不影响。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.entity.constants import BLACKLIST_GLOBAL_SCOPE


class BlacklistStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = BlacklistStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_not_blocked(self) -> None:
        self.assertFalse(self.store.is_in("123", "10001"))
        self.assertFalse(self.store.is_blocked("123", "10001"))

    async def test_add_then_in_group(self) -> None:
        added = await self.store.add("123", "10001")
        self.assertTrue(added)
        self.assertTrue(self.store.is_in("123", "10001"))
        self.assertTrue(self.store.is_blocked("123", "10001"))
        # 别的群没有这条，不能误伤
        self.assertFalse(self.store.is_in("456", "10001"))
        self.assertFalse(self.store.is_blocked("456", "10001"))

    async def test_duplicate_add_is_false(self) -> None:
        await self.store.add("123", "10001")
        added = await self.store.add("123", "10001")
        self.assertFalse(added)
        self.assertEqual(self.store.list_user_ids("123"), ["10001"])

    async def test_global_blocks_every_group(self) -> None:
        await self.store.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        self.assertTrue(self.store.is_blocked("123", "10001"))
        self.assertTrue(self.store.is_blocked("456", "10001"))
        # 全局名单和群名单分开列
        self.assertEqual(self.store.list_user_ids(BLACKLIST_GLOBAL_SCOPE), ["10001"])
        self.assertEqual(self.store.list_user_ids("123"), [])

    async def test_remove_only_that_list(self) -> None:
        await self.store.add("123", "10001")
        await self.store.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        removed = await self.store.remove("123", "10001")
        self.assertTrue(removed)
        self.assertFalse(self.store.is_in("123", "10001"))
        # 群名单删了，全局还在，本群仍算拉黑
        self.assertTrue(self.store.is_blocked("123", "10001"))

    async def test_remove_missing_is_false(self) -> None:
        removed = await self.store.remove("123", "10001")
        self.assertFalse(removed)

    async def test_survives_reopen(self) -> None:
        await self.store.add("123", "10001")
        reopened = BlacklistStore(self.db_path)
        self.assertTrue(reopened.is_in("123", "10001"))
