# 别人解禁才当通过；机器人自己解、到期、新禁言都不算。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_unmute import is_admin_unmute


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有消息对象时不是通知
        if has_obj:
            self.message_obj = FakeMessage(raw)
        else:
            self.message_obj = None


class VerifyUnmuteTest(unittest.TestCase):
    def test_other_admin_lift_is_unmute(self) -> None:
        event = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": "10086",
                "user_id": "10001",
            }
        )
        self.assertTrue(is_admin_unmute(event, "999"))

    def test_bot_self_lift_is_not_unmute(self) -> None:
        event = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": "999",
            }
        )
        self.assertFalse(is_admin_unmute(event, "999"))

    def test_expiry_and_ban_are_not_unmute(self) -> None:
        expiry = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "lift_ban",
                "operator_id": "0",
            }
        )
        ban = FakeEvent(
            {
                "notice_type": "group_ban",
                "sub_type": "ban",
                "operator_id": "10086",
            }
        )
        decrease = FakeEvent({"notice_type": "group_decrease"})
        self.assertFalse(is_admin_unmute(expiry, "999"))
        self.assertFalse(is_admin_unmute(ban, "999"))
        self.assertFalse(is_admin_unmute(decrease, "999"))
        self.assertFalse(is_admin_unmute(FakeEvent(has_obj=False), "999"))
