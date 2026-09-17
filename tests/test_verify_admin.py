# 入群验证管理：管理员通过、拒绝、扫描本群 pending。不踢人。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_admin import (
    REJECT_MESSAGE,
    pass_user,
    reject_user,
    scan_users,
)
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore


class FakeEvent:
    """只提供管理员身份，验证权限边界。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        return self._admin


class VerifyAdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VerifyStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_pass_deletes_and_returns_unmute_id(self) -> None:
        await self.store.put("123", "10001", "123456")
        message, unmute = await pass_user(self.store, self.event, "123", "  10001  ")
        self.assertEqual(message, "已通过入群验证：10001")
        self.assertEqual(unmute, "10001")
        self.assertEqual(self.store.get_code("123", "10001"), "")

    async def test_pass_missing_and_bad_id(self) -> None:
        missing, unmute = await pass_user(self.store, self.event, "123", "10001")
        empty, empty_unmute = await pass_user(self.store, self.event, "123", "  ")
        bad, bad_unmute = await pass_user(self.store, self.event, "123", "张三")
        self.assertEqual(missing, "不在待验证名单里：10001")
        self.assertEqual(unmute, "")
        self.assertEqual(empty, "请提供 QQ 号。")
        self.assertEqual(empty_unmute, "")
        self.assertEqual(bad, "QQ 号必须是数字。")
        self.assertEqual(bad_unmute, "")

    async def test_pass_does_not_touch_other_group(self) -> None:
        await self.store.put("111", "10001", "111111")
        await self.store.put("222", "10001", "222222")
        message, unmute = await pass_user(self.store, self.event, "111", "10001")
        self.assertEqual(unmute, "10001")
        self.assertIn("已通过", message)
        self.assertEqual(self.store.get_code("222", "10001"), "222222")

    async def test_reject_deletes_without_unmute(self) -> None:
        await self.store.put("123", "10001", "123456")
        message = await reject_user(self.store, self.event, "123", "10001")
        self.assertEqual(message, "已拒绝入群验证：10001（未踢出）")
        self.assertEqual(self.store.get_code("123", "10001"), "")
        missing = await reject_user(self.store, self.event, "123", "10001")
        self.assertEqual(missing, "不在待验证名单里：10001")

    async def test_scan_lists_only_this_group(self) -> None:
        await self.store.put("123", "10002", "222222")
        await self.store.put("123", "10001", "111111")
        await self.store.put("999", "10003", "333333")
        text, ids = scan_users(self.store, self.event, "123")
        self.assertEqual(ids, ["10001", "10002"])
        self.assertIn("10001", text)
        self.assertIn("10002", text)
        self.assertNotIn("10003", text)
        empty_text, empty_ids = scan_users(self.store, self.event, "555")
        self.assertEqual(empty_text, "本群没有待验证的人。")
        self.assertEqual(empty_ids, [])

    async def test_non_admin_is_rejected(self) -> None:
        guest = FakeEvent(admin=False)
        await self.store.put("123", "10001", "123456")
        passed, unmute = await pass_user(self.store, guest, "123", "10001")
        rejected = await reject_user(self.store, guest, "123", "10001")
        scanned, ids = scan_users(self.store, guest, "123")
        self.assertEqual(passed, REJECT_MESSAGE)
        self.assertEqual(unmute, "")
        self.assertEqual(rejected, REJECT_MESSAGE)
        self.assertEqual(scanned, REJECT_MESSAGE)
        self.assertEqual(ids, [])
        self.assertEqual(self.store.get_code("123", "10001"), "123456")
