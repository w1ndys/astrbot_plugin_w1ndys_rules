# OneBot 原始消息里的群角色。读不到就当普通群员。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.qq_role import (
    is_qq_group_staff,
    speaker_qq_role,
)


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有 message_obj 时完全读不到角色
        if has_obj:
            self.message_obj = FakeMessage(raw)
        # 残缺事件按读不到处理，不能当成群管
        else:
            self.message_obj = None


class SenderObj:
    def __init__(self, role: str) -> None:
        self.role = role


class RawWithSenderAttr:
    def __init__(self, sender) -> None:
        self.sender = sender


class QqRoleTest(unittest.TestCase):
    def test_dict_owner(self) -> None:
        event = FakeEvent({"sender": {"role": "owner"}})
        self.assertEqual(speaker_qq_role(event), "owner")
        self.assertTrue(is_qq_group_staff(event))

    def test_dict_admin_casefold(self) -> None:
        event = FakeEvent({"sender": {"role": "Admin"}})
        self.assertTrue(is_qq_group_staff(event))

    def test_member_is_not_staff(self) -> None:
        event = FakeEvent({"sender": {"role": "member"}})
        self.assertFalse(is_qq_group_staff(event))

    def test_missing_raw_is_not_staff(self) -> None:
        event = FakeEvent(has_obj=False)
        self.assertEqual(speaker_qq_role(event), "")
        self.assertFalse(is_qq_group_staff(event))

    def test_event_sender_attr(self) -> None:
        event = FakeEvent(RawWithSenderAttr({"role": "admin"}))
        self.assertTrue(is_qq_group_staff(event))

    def test_object_sender_role(self) -> None:
        event = FakeEvent(RawWithSenderAttr(SenderObj("owner")))
        self.assertTrue(is_qq_group_staff(event))
