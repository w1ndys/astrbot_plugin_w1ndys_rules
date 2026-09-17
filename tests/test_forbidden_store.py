# 违禁配置数据层：触发词和样本按群、按类型隔离并持久化。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_KIND_SAMPLE,
    FORBIDDEN_KIND_TRIGGER,
)


class ForbiddenStoreTest(unittest.IsolatedAsyncioTestCase):
    """用真实临时 SQLite 验证存储行为，不模拟数据库。"""

    def setUp(self) -> None:
        """每个测试使用独立数据库，避免测试间串数据。"""
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = ForbiddenStore(self.db_path)

    def tearDown(self) -> None:
        """测试结束后删除临时数据库。"""
        self._tmp.cleanup()

    async def test_add_and_reload_keeps_group_and_kind_isolation(self) -> None:
        """同一内容可分别属于不同群和不同类型，重开后仍存在。"""
        self.assertTrue(await self.store.add("100", FORBIDDEN_KIND_TRIGGER, "广告"))
        self.assertTrue(await self.store.add("100", FORBIDDEN_KIND_SAMPLE, "卖课私聊"))
        self.assertTrue(await self.store.add("200", FORBIDDEN_KIND_TRIGGER, "广告"))

        reloaded = ForbiddenStore(self.db_path)

        self.assertEqual(
            reloaded.list_contents("100", FORBIDDEN_KIND_TRIGGER), ["广告"]
        )
        self.assertEqual(
            reloaded.list_contents("100", FORBIDDEN_KIND_SAMPLE), ["卖课私聊"]
        )
        self.assertEqual(
            reloaded.list_contents("200", FORBIDDEN_KIND_TRIGGER), ["广告"]
        )

    async def test_add_duplicate_returns_false_without_duplicate_row(self) -> None:
        """同群同类型的相同内容只能保存一次。"""
        self.assertTrue(await self.store.add("100", FORBIDDEN_KIND_TRIGGER, "广告"))
        self.assertFalse(await self.store.add("100", FORBIDDEN_KIND_TRIGGER, "广告"))

        self.assertEqual(
            self.store.list_contents("100", FORBIDDEN_KIND_TRIGGER), ["广告"]
        )

    async def test_update_reports_missing_conflict_and_success(self) -> None:
        """修改要区分原内容不存在、新内容冲突和修改成功。"""
        await self.store.add("100", FORBIDDEN_KIND_TRIGGER, "广告")
        await self.store.add("100", FORBIDDEN_KIND_TRIGGER, "加群")

        self.assertEqual(
            await self.store.update("100", FORBIDDEN_KIND_TRIGGER, "不存在", "新词"),
            "missing",
        )
        self.assertEqual(
            await self.store.update("100", FORBIDDEN_KIND_TRIGGER, "广告", "加群"),
            "conflict",
        )
        self.assertEqual(
            await self.store.update("100", FORBIDDEN_KIND_TRIGGER, "广告", "推广"),
            "updated",
        )
        self.assertEqual(
            self.store.list_contents("100", FORBIDDEN_KIND_TRIGGER),
            ["加群", "推广"],
        )

    async def test_delete_reports_whether_row_existed(self) -> None:
        """删除不存在的数据不能回报成功。"""
        await self.store.add("100", FORBIDDEN_KIND_SAMPLE, "卖课私聊")

        self.assertFalse(
            await self.store.delete("100", FORBIDDEN_KIND_SAMPLE, "不存在")
        )
        self.assertTrue(
            await self.store.delete("100", FORBIDDEN_KIND_SAMPLE, "卖课私聊")
        )
        self.assertEqual(self.store.list_contents("100", FORBIDDEN_KIND_SAMPLE), [])
