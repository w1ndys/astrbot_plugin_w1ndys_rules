# 违禁配置管理：管理员通过 Agent 对本群触发词和样本增删改查。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_admin import (
    REJECT_MESSAGE,
    add_item,
    delete_item,
    list_items,
    update_item,
)
from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.entity.constants import FORBIDDEN_ITEM_MAX_LEN


class FakeEvent:
    """只提供管理员身份，验证权限边界。"""

    def __init__(self, admin: bool = True) -> None:
        """保存测试指定的管理员状态。"""
        self._admin = admin

    def is_admin(self) -> bool:
        """返回测试指定的管理员状态。"""
        return self._admin


class ForbiddenAdminTest(unittest.IsolatedAsyncioTestCase):
    """验证自然语言工具背后的业务规则和回报文案。"""

    def setUp(self) -> None:
        """每个测试使用独立数据库。"""
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()
        self.group_id = "123456"

    def tearDown(self) -> None:
        """删除测试数据库。"""
        self._tmp.cleanup()

    async def test_add_trigger_and_sample(self) -> None:
        """两类中文类型名都能新增，回报要带最终入库内容。"""
        trigger = await add_item(
            self.store, self.event, self.group_id, "触发词", "  广告  "
        )
        sample = await add_item(
            self.store, self.event, self.group_id, "违禁样本", "卖课私聊"
        )

        self.assertEqual(trigger, "已添加违禁触发词「广告」。")
        self.assertEqual(sample, "已添加违禁样本「卖课私聊」。")

    async def test_add_rejects_duplicate_invalid_kind_and_bad_content(self) -> None:
        """重复、错误类型、空内容和超长内容都不能写库。"""
        await add_item(self.store, self.event, self.group_id, "触发词", "广告")

        duplicate = await add_item(
            self.store, self.event, self.group_id, "触发词", "广告"
        )
        invalid = await add_item(self.store, self.event, self.group_id, "规则", "广告")
        empty = await add_item(self.store, self.event, self.group_id, "触发词", "  ")
        too_long = await add_item(
            self.store,
            self.event,
            self.group_id,
            "触发词",
            "a" * (FORBIDDEN_ITEM_MAX_LEN + 1),
        )

        self.assertIn("已经存在", duplicate)
        self.assertIn("只能是", invalid)
        self.assertIn("不能为空", empty)
        self.assertIn(f"最多 {FORBIDDEN_ITEM_MAX_LEN}", too_long)

    async def test_update_does_not_turn_missing_into_add(self) -> None:
        """修改不存在的内容要明确失败，不能悄悄新增。"""
        message = await update_item(
            self.store,
            self.event,
            self.group_id,
            "触发词",
            "不存在",
            "新词",
        )

        self.assertEqual(message, "本群没有违禁触发词「不存在」，没有修改。")
        self.assertEqual(await self._list(), "本群还没有违禁触发词或违禁样本。")

    async def test_update_reports_conflict_no_change_and_success(self) -> None:
        """修改要区分冲突、内容未变和成功。"""
        await add_item(self.store, self.event, self.group_id, "触发词", "广告")
        await add_item(self.store, self.event, self.group_id, "触发词", "加群")

        conflict = await update_item(
            self.store, self.event, self.group_id, "触发词", "广告", "加群"
        )
        unchanged = await update_item(
            self.store, self.event, self.group_id, "触发词", "广告", "广告"
        )
        updated = await update_item(
            self.store, self.event, self.group_id, "触发词", "广告", "推广"
        )

        self.assertIn("已经存在", conflict)
        self.assertIn("没有改动", unchanged)
        self.assertEqual(updated, "已将违禁触发词「广告」修改为「推广」。")

    async def test_delete_and_list(self) -> None:
        """查询同时列出两类数据，删除要如实报告是否存在。"""
        await add_item(self.store, self.event, self.group_id, "触发词", "广告")
        await add_item(self.store, self.event, self.group_id, "违禁样本", "卖课私聊")

        listed = await self._list()
        missing = await delete_item(
            self.store, self.event, self.group_id, "触发词", "不存在"
        )
        removed = await delete_item(
            self.store, self.event, self.group_id, "触发词", "广告"
        )

        self.assertIn("违禁触发词（1 条）", listed)
        self.assertIn("「广告」", listed)
        self.assertIn("违禁样本（1 条）", listed)
        self.assertIn("「卖课私聊」", listed)
        self.assertIn("没有删除", missing)
        self.assertEqual(removed, "已删除违禁触发词「广告」。")

    async def test_non_admin_cannot_read_or_write(self) -> None:
        """非管理员不能通过工具读取或修改本群规则。"""
        event = FakeEvent(False)

        added = await add_item(self.store, event, self.group_id, "触发词", "广告")
        listed = list_items(self.store, event, self.group_id)

        self.assertEqual(added, REJECT_MESSAGE)
        self.assertEqual(listed, REJECT_MESSAGE)

    async def _list(self) -> str:
        """统一调用同步列表函数，便于异步测试里断言。"""
        return list_items(self.store, self.event, self.group_id)
