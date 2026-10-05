# OneBot 原始消息里的群角色和群昵称。读不到就当普通群员、昵称留空。

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
    speaker_display_name,
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

    def test_display_name_prefers_card(self) -> None:
        """群名片优先于 QQ 昵称。"""
        event = FakeEvent({"sender": {"card": "小明", "nickname": "nick"}})
        self.assertEqual(speaker_display_name(event), "小明")

    def test_display_name_falls_back_to_nickname(self) -> None:
        """群名片为空或只有空白时用 QQ 昵称。"""
        event = FakeEvent({"sender": {"card": "   ", "nickname": "nick"}})
        self.assertEqual(speaker_display_name(event), "nick")

    def test_display_name_empty_when_both_blank(self) -> None:
        """名片和昵称都没有时返回空串，处置照常继续。"""
        event = FakeEvent({"sender": {"card": "", "nickname": ""}})
        self.assertEqual(speaker_display_name(event), "")

    def test_display_name_without_sender(self) -> None:
        """没有消息对象或原始消息里没有 sender，都返回空串。"""
        self.assertEqual(speaker_display_name(FakeEvent(has_obj=False)), "")
        self.assertEqual(speaker_display_name(FakeEvent({"post_type": "message"})), "")
