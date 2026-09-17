# 退群清 pending：group_decrease 才认；没 pending 不动库。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_leave import (
    drop_pending,
    is_group_decrease,
)
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有消息对象时不是退群通知
        if has_obj:
            self.message_obj = FakeMessage(raw)
        else:
            self.message_obj = None


class VerifyLeaveTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = VerifyStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_notice_is_group_decrease(self) -> None:
        event = FakeEvent({"notice_type": "group_decrease", "user_id": "10001"})
        self.assertTrue(is_group_decrease(event))

    def test_increase_and_plain_are_not_decrease(self) -> None:
        self.assertFalse(
            is_group_decrease(FakeEvent({"notice_type": "group_increase"}))
        )
        self.assertFalse(is_group_decrease(FakeEvent({"post_type": "message"})))
        self.assertFalse(is_group_decrease(FakeEvent(has_obj=False)))

    async def test_drop_deletes_only_that_user(self) -> None:
        await self.store.put("123", "10001", "111111")
        await self.store.put("123", "10002", "222222")
        dropped = await drop_pending(self.store, "123", "10001")
        self.assertTrue(dropped)
        self.assertEqual(self.store.get_code("123", "10001"), "")
        self.assertEqual(self.store.get_code("123", "10002"), "222222")

    async def test_drop_missing_is_false(self) -> None:
        dropped = await drop_pending(self.store, "123", "10001")
        empty = await drop_pending(self.store, "123", "")
        self.assertFalse(dropped)
        self.assertFalse(empty)
