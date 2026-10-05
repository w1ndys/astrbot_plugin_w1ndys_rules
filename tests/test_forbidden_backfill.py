# 违禁日志群昵称回补：协议资料收成规则、只填空值、文案。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_backfill import (
    backfill_group,
    backfill_message,
    member_names,
    pending_backfill_groups,
)
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import FORBIDDEN_REASON_MODEL


class MemberNamesTest(unittest.TestCase):
    """get_group_member_list 回报收成 {QQ: 群昵称}。"""

    def test_card_preferred_over_nickname(self) -> None:
        """成员资料里群名片优先，没有名片用 QQ 昵称。"""
        raw = {
            "data": [
                {"user_id": 1, "card": "小明", "nickname": "nick"},
                {"user_id": 2, "card": "", "nickname": "nick2"},
            ]
        }
        self.assertEqual(member_names(raw), {"1": "小明", "2": "nick2"})

    def test_members_without_name_dropped(self) -> None:
        """名片和昵称都空、没有 QQ 的成员不进待填表。"""
        raw = [
            {"user_id": 3, "card": "  ", "nickname": ""},
            {"card": "没有QQ"},
            "不是对象",
        ]
        self.assertEqual(member_names(raw), {})

    def test_unknown_shape_is_empty(self) -> None:
        """协议回报形状不认识时当没有成员。"""
        self.assertEqual(member_names(None), {})
        self.assertEqual(member_names({"data": "x"}), {})


class BackfillStoreTest(unittest.IsolatedAsyncioTestCase):
    """按群回补：只填空昵称，某群没拉到资料不影响其他群。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenLogStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_backfill_group_fills_empty_only(self) -> None:
        """已写过的昵称不动，写入条数只算空行。"""
        await self.store.insert(
            "111", "1", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]", "旧"
        )
        await self.store.insert(
            "111", "2", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        raw = {
            "data": [
                {"user_id": 1, "card": "新", "nickname": ""},
                {"user_id": 2, "card": "", "nickname": "小刚"},
            ]
        }
        written = await backfill_group(self.store, "111", raw)
        self.assertEqual(written, 1)
        self.assertEqual(self.store.get(1).sender_name, "旧")
        self.assertEqual(self.store.get(2).sender_name, "小刚")

    async def test_failed_group_leaves_pending(self) -> None:
        """一个群没拉到资料时不调回补，它仍留在待补清单里，别的群照补。"""
        await self.store.insert(
            "111", "1", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        await self.store.insert(
            "222", "2", FORBIDDEN_REASON_MODEL, "a", "t", "[]", "[]"
        )
        self.assertEqual(pending_backfill_groups(self.store), ["111", "222"])
        await backfill_group(self.store, "222", {"data": [{"user_id": 2, "card": "小刚"}]})
        self.assertEqual(self.store.get(2).sender_name, "小刚")
        self.assertEqual(self.store.get(1).sender_name, "")
        self.assertEqual(pending_backfill_groups(self.store), ["111"])


class BackfillMessageTest(unittest.TestCase):
    """回补结果文案。"""

    def test_message_lists_failed_groups(self) -> None:
        """文案带写入条数；有失败群就把群号列出来。"""
        self.assertEqual(backfill_message(3, []), "已回补 3 条群昵称。")
        message = backfill_message(0, [{"group_id": "111", "reason": "拉取失败"}])
        self.assertIn("111", message)
        self.assertIn("0 条", message)
