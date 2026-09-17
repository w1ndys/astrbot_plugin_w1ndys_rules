# 黑名单管理：管理员通过 Agent 对本群或全局名单增删查。不踢人。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.blacklist_admin import (
    REJECT_MESSAGE,
    add_user,
    delete_user,
    list_users,
)
from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.entity.constants import BLACKLIST_GLOBAL_SCOPE


class FakeEvent:
    """只提供管理员身份，验证权限边界。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        return self._admin


class BlacklistAdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = BlacklistStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_add_strips_and_reports(self) -> None:
        message = await add_user(self.store, self.event, "123", "  10001  ")
        self.assertEqual(message, "已加入本群黑名单：10001")
        self.assertTrue(self.store.is_in("123", "10001"))

    async def test_add_rejects_duplicate_empty_and_non_digit(self) -> None:
        await add_user(self.store, self.event, "123", "10001")
        duplicate = await add_user(self.store, self.event, "123", "10001")
        empty = await add_user(self.store, self.event, "123", "  ")
        bad = await add_user(self.store, self.event, "123", "张三")
        self.assertEqual(duplicate, "已经在本群黑名单里：10001")
        self.assertEqual(empty, "请提供 QQ 号。")
        self.assertEqual(bad, "QQ 号必须是数字。")

    async def test_global_does_not_write_group_list(self) -> None:
        message = await add_user(
            self.store, self.event, BLACKLIST_GLOBAL_SCOPE, "10001"
        )
        self.assertEqual(message, "已加入全局黑名单：10001")
        self.assertEqual(list_users(self.store, self.event, "123"), "本群黑名单是空的。")
        listed = list_users(self.store, self.event, BLACKLIST_GLOBAL_SCOPE)
        self.assertIn("10001", listed)
        self.assertIn("全局黑名单", listed)

    async def test_delete_only_that_list(self) -> None:
        await add_user(self.store, self.event, "123", "10001")
        await add_user(self.store, self.event, BLACKLIST_GLOBAL_SCOPE, "10001")
        message = await delete_user(self.store, self.event, "123", "10001")
        self.assertEqual(message, "已从本群黑名单移除：10001")
        missing = await delete_user(self.store, self.event, "123", "10001")
        self.assertEqual(missing, "不在本群黑名单里：10001")
        self.assertTrue(self.store.is_in(BLACKLIST_GLOBAL_SCOPE, "10001"))

    async def test_non_admin_is_rejected(self) -> None:
        guest = FakeEvent(admin=False)
        added = await add_user(self.store, guest, "123", "10001")
        listed = list_users(self.store, guest, "123")
        deleted = await delete_user(self.store, guest, "123", "10001")
        self.assertEqual(added, REJECT_MESSAGE)
        self.assertEqual(listed, REJECT_MESSAGE)
        self.assertEqual(deleted, REJECT_MESSAGE)
        self.assertFalse(self.store.is_in("123", "10001"))

    async def test_list_includes_everyone(self) -> None:
        await add_user(self.store, self.event, "123", "10001")
        await add_user(self.store, self.event, "123", "10002")
        listed = list_users(self.store, self.event, "123")
        self.assertEqual(listed, "本群黑名单（2 人）：\n10001\n10002")
