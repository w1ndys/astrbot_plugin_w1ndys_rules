# 邀请树页：跨群找树、从根展开、成环截断、节点上限和全部记录分页。

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.invite_tree import (
    list_edges_page,
    search_trees,
)
from astrbot_plugin_w1ndys_rules.data.invite_store import InviteStore


class InviteTreeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = InviteStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_search_trees_across_groups(self) -> None:
        await self.store.record("111", "10001", "10086", "invite")
        await self.store.record("111", "10086", "20002", "invite")
        await self.store.record("222", "10001", "30003", "invite")
        ok, result = search_trees(self.store, "10001")
        self.assertTrue(ok)
        self.assertEqual(result["user_id"], "10001")
        self.assertEqual([g["group_id"] for g in result["groups"]], ["111", "222"])
        tree = result["groups"][0]
        # 从本人往上追到没有邀请人的 20002，再从根往下展开
        self.assertEqual(tree["root_id"], "20002")
        root = tree["nodes"][0]
        self.assertEqual(root["user_id"], "20002")
        middle = root["children"][0]
        self.assertEqual(middle["user_id"], "10086")
        target = middle["children"][0]
        self.assertEqual(target["user_id"], "10001")
        self.assertTrue(target["is_target"])
        self.assertFalse(root["is_target"])

    async def test_target_without_inviter_is_root(self) -> None:
        await self.store.record("111", "20002", "10001", "invite")
        ok, result = search_trees(self.store, "10001")
        self.assertTrue(ok)
        tree = result["groups"][0]
        # 本人没有邀请边，自己就是根，下线照常展开
        self.assertEqual(tree["root_id"], "10001")
        self.assertEqual(tree["nodes"][0]["children"][0]["user_id"], "20002")

    async def test_cycle_terminates(self) -> None:
        await self.store.record("111", "10001", "10086", "invite")
        await self.store.record("111", "10086", "10001", "invite")
        ok, result = search_trees(self.store, "10001")
        self.assertTrue(ok)
        tree = result["groups"][0]
        root = tree["nodes"][0]
        # 成环时停在重复节点，只保留两个人
        self.assertEqual(tree["root_id"], "10086")
        self.assertEqual(len(root["children"]), 1)
        self.assertEqual(root["children"][0]["children"], [])

    async def test_missing_user_returns_no_groups(self) -> None:
        ok, result = search_trees(self.store, "10001")
        self.assertTrue(ok)
        self.assertEqual(result["groups"], [])

    async def test_bad_user_id(self) -> None:
        ok, message = search_trees(self.store, "")
        self.assertFalse(ok)
        self.assertEqual(message, "请提供 QQ 号。")
        ok, message = search_trees(self.store, "张三")
        self.assertFalse(ok)
        self.assertEqual(message, "QQ 号必须是数字。")

    async def test_tree_truncates_at_limit(self) -> None:
        await self.store.record("111", "20001", "10000", "invite")
        await self.store.record("111", "20002", "10000", "invite")
        await self.store.record("111", "20003", "10000", "invite")
        # 把上限压到 2，验证只画根加一个孩子
        with patch(
            "astrbot_plugin_w1ndys_rules.business.invite_tree.INVITE_TREE_NODE_LIMIT",
            2,
        ):
            ok, result = search_trees(self.store, "10000")
        self.assertTrue(ok)
        tree = result["groups"][0]
        self.assertTrue(tree["truncated"])
        self.assertEqual(len(tree["nodes"][0]["children"]), 1)

    async def test_list_edges_page_filters(self) -> None:
        for i in range(3):
            await self.store.record("123", str(30000 + i), "10086", "invite")
        await self.store.record("999", "40000", "10086", "invite")
        page = list_edges_page(self.store, {"group_id": "123", "page_size": 2})
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 2)
        page = list_edges_page(self.store, {"group_id": "999"})
        self.assertEqual(page["total"], 1)
        page = list_edges_page(self.store, {"user_id": "10086"})
        self.assertEqual(page["total"], 4)

    async def test_list_edges_page_bounds(self) -> None:
        await self.store.record("123", "10001", "10086", "invite")
        # 坏页码回到第一页，每页最多 100
        page = list_edges_page(
            self.store, {"page": "abc", "page_size": 500}
        )
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 100)
        self.assertEqual(page["items"][0]["inviter_id"], "10086")
