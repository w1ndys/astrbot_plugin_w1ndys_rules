# 白名单按群存，全局用固定 group_id。群与群互不影响。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.whitelist_store import WhitelistStore
from astrbot_plugin_w1ndys_rules.entity.constants import BLACKLIST_GLOBAL_SCOPE


class WhitelistStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = WhitelistStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_not_listed(self) -> None:
        self.assertFalse(self.store.is_in("123", "10001"))
        self.assertFalse(self.store.is_listed("123", "10001"))

    async def test_group_row_touches_one_group_only(self) -> None:
        """A 群的行让 A 群为真，B 群仍为假。"""
        added = await self.store.add("123", "10001")
        self.assertTrue(added)
        self.assertTrue(self.store.is_in("123", "10001"))
        self.assertTrue(self.store.is_listed("123", "10001"))
        self.assertFalse(self.store.is_in("456", "10001"))
        self.assertFalse(self.store.is_listed("456", "10001"))

    async def test_global_row_lists_every_group(self) -> None:
        """global 行使任意群 is_listed 为真，但不是别的群自己的行。"""
        await self.store.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        self.assertTrue(self.store.is_listed("123", "10001"))
        self.assertTrue(self.store.is_listed("456", "10001"))
        self.assertFalse(self.store.is_in("123", "10001"))

    async def test_duplicate_add_is_false(self) -> None:
        await self.store.add("123", "10001")
        added = await self.store.add("123", "10001")
        self.assertFalse(added)

    async def test_remove_twice(self) -> None:
        await self.store.add("123", "10001")
        removed = await self.store.remove("123", "10001")
        self.assertTrue(removed)
        self.assertFalse(self.store.is_in("123", "10001"))
        again = await self.store.remove("123", "10001")
        self.assertFalse(again)

    async def test_remove_leaves_other_scope(self) -> None:
        await self.store.add("123", "10001")
        await self.store.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        removed = await self.store.remove("123", "10001")
        self.assertTrue(removed)
        self.assertFalse(self.store.is_in("123", "10001"))
        # 全局那一行还在，所以本群仍算已加白
        self.assertTrue(self.store.is_listed("123", "10001"))

    async def test_survives_reopen(self) -> None:
        await self.store.add("123", "10001")
        reopened = WhitelistStore(self.db_path)
        self.assertTrue(reopened.is_in("123", "10001"))
