# 群名片拦截：按真实群名片结构识别，名单外的群不处置，群主管理员跳过。

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.group_card import (
    handle_group_card,
    is_group_card,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
)


# 结构来自真实群名片 payload，查询串改成占位，避免把签名写进仓库。
GROUP_CARD = {
    "app": "com.tencent.contact.lua",
    "prompt": "群名片: 卷心菜大军",
    "bizsrc": "qun.share",
    "meta": {
        "contact": {
            "nickname": "卷心菜大军",
            "tag": "群名片",
            "jumpUrl": "mqqapi://card/show_pslcard?authSig=SECRET",
        }
    },
    "view": "contact",
}

NEWS_CARD = {
    "prompt": "[分享]某新闻",
    "meta": {
        "news": {
            "title": "某新闻标题",
            "desc": "某新闻摘要",
        }
    },
}


class Json:
    """AstrBot Json 组件替身，按类名识别。"""

    def __init__(self, data) -> None:
        self.data = data


class Plain:
    """普通文本段，不能当成群名片。"""

    def __init__(self, text: str) -> None:
        self.text = text


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeMessage:
    def __init__(self, message_id=88, role: str = "") -> None:
        self.message_id = message_id
        self.raw_message = {"sender": {"role": role}}


class FakeEvent:
    def __init__(self, messages=None, role: str = "") -> None:
        self.bot = FakeBot()
        self.message_obj = FakeMessage(role=role)
        self._messages = messages or []

    def get_sender_id(self) -> str:
        return "10001"

    def get_self_id(self) -> str:
        return "999"

    def get_messages(self):
        return self._messages


def on_config() -> dict:
    return {
        FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS: "123",
        FORBIDDEN_CFG_MUTE_SECONDS: 60,
        FORBIDDEN_CFG_REMIND_TEXT: "不要发群名片。",
    }


class GroupCardDetectTest(unittest.TestCase):
    def test_real_group_card(self) -> None:
        event = FakeEvent([Json({"data": json.dumps(GROUP_CARD, ensure_ascii=False)})])
        self.assertTrue(is_group_card(event))

    def test_news_card_is_not_group_card(self) -> None:
        event = FakeEvent([Json(NEWS_CARD)])
        self.assertFalse(is_group_card(event))

    def test_plain_text_is_not_group_card(self) -> None:
        event = FakeEvent([Plain("群名片")])
        self.assertFalse(is_group_card(event))

    def test_no_messages(self) -> None:
        self.assertFalse(is_group_card(object()))


class GroupCardHandleTest(unittest.IsolatedAsyncioTestCase):
    async def test_switch_off_skips(self) -> None:
        event = FakeEvent([Json(GROUP_CARD)])
        handled, reply = await handle_group_card({}, event, "123")
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(event.bot.api.calls, [])

    async def test_other_group_skips(self) -> None:
        event = FakeEvent([Json(GROUP_CARD)])
        handled, reply = await handle_group_card(on_config(), event, "999")
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(event.bot.api.calls, [])

    async def test_hit_recalls(self) -> None:
        event = FakeEvent([Json(GROUP_CARD)])
        handled, reply = await handle_group_card(on_config(), event, "123")
        self.assertTrue(handled)
        self.assertEqual(reply, "不要发群名片。")
        actions = [name for name, _kwargs in event.bot.api.calls]
        self.assertIn("delete_msg", actions)
        self.assertIn("set_group_ban", actions)

    async def test_owner_skips(self) -> None:
        event = FakeEvent([Json(GROUP_CARD)], role="owner")
        handled, reply = await handle_group_card(on_config(), event, "123")
        self.assertFalse(handled)
        self.assertEqual(reply, "")
        self.assertEqual(event.bot.api.calls, [])
