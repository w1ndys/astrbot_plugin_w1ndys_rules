# 违禁日志页的名单按钮：号码校验、范围互斥、文案和四个状态。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_log_page import list_logs
from astrbot_plugin_w1ndys_rules.business.whitelist import (
    PAIR_ERROR,
    add_blacklist,
    add_whitelist,
    remove_blacklist,
    remove_whitelist,
    should_skip_forbidden,
)
from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.data.whitelist_store import WhitelistStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    BLACKLIST_GLOBAL_SCOPE,
    FORBIDDEN_REASON_MODEL,
)


class WhitelistPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.whitelist = WhitelistStore(db_path)
        self.blacklist = BlacklistStore(db_path)
        self.logs = ForbiddenLogStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_bad_pair_rejected(self) -> None:
        """空号码、星号范围、中文 QQ 都不写库。"""
        bad = [
            {"group_id": "123", "user_id": ""},
            {"group_id": "*", "user_id": "10001"},
            {"group_id": "123", "user_id": "张三"},
            {"group_id": "global-list", "user_id": "10001"},
        ]
        for payload in bad:
            ok, message = await add_whitelist(
                self.whitelist, self.blacklist, payload
            )
            self.assertFalse(ok)
            self.assertEqual(message, PAIR_ERROR)
        self.assertFalse(self.whitelist.is_in("*", "10001"))

    async def test_global_scope_can_be_written(self) -> None:
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {
                "group_id": BLACKLIST_GLOBAL_SCOPE,
                "user_id": "10001",
                "source_group_id": "123",
            },
        )
        self.assertTrue(ok)
        self.assertEqual(result["message"], "已加入全局白名单。")
        self.assertTrue(self.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))

    async def test_group_scope_stays_in_one_group(self) -> None:
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertTrue(ok)
        self.assertEqual(result["message"], "已加入本群白名单。")
        self.assertTrue(self.whitelist.is_in("123", "10001"))
        # 别群和全局都不该出现这一行
        self.assertFalse(self.whitelist.is_in("456", "10001"))
        self.assertFalse(self.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))

    async def test_already_in_reports_plain_message(self) -> None:
        await self.whitelist.add("123", "10001")
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertTrue(ok)
        self.assertEqual(result["message"], "已在本群白名单。")

    async def test_global_whitelist_lists_every_group(self) -> None:
        await add_whitelist(
            self.whitelist,
            self.blacklist,
            {
                "group_id": BLACKLIST_GLOBAL_SCOPE,
                "user_id": "10001",
                "source_group_id": "123",
            },
        )
        self.assertTrue(self.whitelist.is_listed("123", "10001"))
        self.assertTrue(self.whitelist.is_listed("456", "10001"))

    async def test_scope_exclusive_both_orders(self) -> None:
        """先白后黑、先黑后白都只清同一个范围。"""
        base = {"user_id": "10001", "source_group_id": "123"}
        await add_whitelist(
            self.whitelist, self.blacklist, {**base, "group_id": "123"}
        )
        await add_blacklist(
            self.whitelist, self.blacklist, {**base, "group_id": "123"}
        )
        self.assertFalse(self.whitelist.is_in("123", "10001"))
        self.assertTrue(self.blacklist.is_in("123", "10001"))
        await add_blacklist(
            self.whitelist,
            self.blacklist,
            {**base, "group_id": BLACKLIST_GLOBAL_SCOPE},
        )
        await add_whitelist(
            self.whitelist,
            self.blacklist,
            {**base, "group_id": BLACKLIST_GLOBAL_SCOPE},
        )
        self.assertFalse(self.blacklist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        self.assertTrue(self.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        # 本群那一行黑名单没被另一边动过
        self.assertTrue(self.blacklist.is_in("123", "10001"))

    async def test_global_blacklist_still_blocks_after_white(self) -> None:
        """只在全局黑名单时加本群白名单，文案要提醒仍不会跳过。"""
        await self.blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertTrue(ok)
        self.assertEqual(
            result["message"],
            "已加入本群白名单。此人仍在黑名单，不会跳过违禁。",
        )
        self.assertTrue(self.whitelist.is_in("123", "10001"))
        self.assertTrue(self.blacklist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))
        self.assertFalse(
            should_skip_forbidden(self.whitelist, self.blacklist, "123", "10001")
        )

    async def test_group_blacklist_still_blocks_after_white(self) -> None:
        """本群黑名单压过本群白名单，也不会被加白清掉再拉黑回来。"""
        await self.blacklist.add("123", "10001")
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {
                "group_id": BLACKLIST_GLOBAL_SCOPE,
                "user_id": "10001",
                "source_group_id": "123",
            },
        )
        self.assertTrue(ok)
        # 本群那一行还在，所以按行上的群号看仍被拉黑
        self.assertIn("不会跳过违禁", result["message"])
        self.assertFalse(
            should_skip_forbidden(self.whitelist, self.blacklist, "123", "10001")
        )

    async def test_remove_missing_reports_false(self) -> None:
        ok, message = await remove_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertFalse(ok)
        self.assertEqual(message, "这个人不在本群白名单。")
        ok, message = await remove_blacklist(
            self.whitelist,
            self.blacklist,
            {
                "group_id": BLACKLIST_GLOBAL_SCOPE,
                "user_id": "10001",
                "source_group_id": "123",
            },
        )
        self.assertFalse(ok)
        self.assertEqual(message, "这个人不在全局黑名单。")

    async def test_remove_leaves_other_scope(self) -> None:
        await self.whitelist.add("123", "10001")
        await self.whitelist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        ok, result = await remove_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertTrue(ok)
        self.assertEqual(result["message"], "已移出本群白名单。")
        self.assertFalse(self.whitelist.is_in("123", "10001"))
        self.assertTrue(self.whitelist.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))

    async def test_reply_carries_four_flags(self) -> None:
        await self.blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        ok, result = await add_whitelist(
            self.whitelist,
            self.blacklist,
            {"group_id": "123", "user_id": "10001", "source_group_id": "123"},
        )
        self.assertTrue(ok)
        self.assertTrue(result["whitelisted"])
        self.assertFalse(result["global_whitelisted"])
        self.assertFalse(result["group_blacklisted"])
        self.assertTrue(result["global_blacklisted"])

    async def test_list_rows_carry_flags_without_text(self) -> None:
        """列表行带四个状态，不带原文三列。"""
        log_id = await self.logs.insert(
            "123",
            "10001",
            FORBIDDEN_REASON_MODEL,
            "文本模型",
            "这里有广告",
            "",
            "[]",
        )
        await self.whitelist.add("123", "10001")
        await self.blacklist.add(BLACKLIST_GLOBAL_SCOPE, "10001")
        data = list_logs(
            self.logs,
            {"page": 1, "page_size": 20},
            whitelist=self.whitelist,
            blacklist=self.blacklist,
        )
        row = data["items"][0]
        self.assertEqual(row["id"], log_id)
        self.assertTrue(row["whitelisted"])
        self.assertFalse(row["global_whitelisted"])
        self.assertFalse(row["group_blacklisted"])
        self.assertTrue(row["global_blacklisted"])
        self.assertNotIn("text", row)
        self.assertNotIn("pictures", row)

    def test_list_without_stores_is_false(self) -> None:
        """没传两个存储时四个状态都是假，旧调用不变。"""
        data = list_logs(self.logs, {"page": 1, "page_size": 20})
        self.assertEqual(data["items"], [])
