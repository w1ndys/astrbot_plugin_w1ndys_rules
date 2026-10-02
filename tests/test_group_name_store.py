# 群号到群名映射表：按群号主键 upsert，没行当空名，批量不删旧行。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.group_name_store import GroupNameStore
from astrbot_plugin_w1ndys_rules.entity.group_name import GroupName


class GroupNameStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = GroupNameStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_is_empty(self) -> None:
        self.assertEqual(self.store.get_name("1127665319"), "")
        self.assertEqual(self.store.list_all(), [])
        self.assertEqual(self.store.as_map(), {})

    async def test_upsert_then_get(self) -> None:
        await self.store.upsert("1127665319", "推荐群聊")
        self.assertEqual(self.store.get_name("1127665319"), "推荐群聊")
        items = self.store.list_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].group_id, "1127665319")
        self.assertEqual(items[0].group_name, "推荐群聊")
        self.assertEqual(self.store.as_map(), {"1127665319": "推荐群聊"})

    async def test_upsert_overwrites_name(self) -> None:
        await self.store.upsert("1", "旧名")
        await self.store.upsert("1", "新名")
        self.assertEqual(self.store.get_name("1"), "新名")
        self.assertEqual(len(self.store.list_all()), 1)

    async def test_upsert_skips_empty_group_id(self) -> None:
        await self.store.upsert("", "不该出现")
        self.assertEqual(self.store.list_all(), [])

    async def test_upsert_many_keeps_old_rows(self) -> None:
        await self.store.upsert("1", "甲")
        await self.store.upsert("2", "乙")
        await self.store.upsert_many([GroupName("2", "乙改"), GroupName("3", "丙")])
        mapping = self.store.as_map()
        self.assertEqual(mapping["1"], "甲")
        self.assertEqual(mapping["2"], "乙改")
        self.assertEqual(mapping["3"], "丙")

    async def test_upsert_many_skips_empty_group_id(self) -> None:
        await self.store.upsert_many(
            [GroupName("", "丢"), GroupName("9", "留")]
        )
        self.assertEqual(self.store.as_map(), {"9": "留"})

    async def test_survives_reopen(self) -> None:
        await self.store.upsert("1", "甲")
        reopened = GroupNameStore(self.db_path)
        self.assertEqual(reopened.get_name("1"), "甲")
