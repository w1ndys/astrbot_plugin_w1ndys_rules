# 管理员才能看原始 payload；没 ID 就翻群历史。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.debug_payload import (
    NO_MATCH,
    NOT_FOUND,
    REJECT_MESSAGE,
    dump_payload,
    inspect_payload,
    match_message,
    reply_id_of,
    to_plain,
)


class FakeReply:
    def __init__(self, message_id: str) -> None:
        self.type = "Reply"
        self.id = message_id


class FakeMessage:
    def __init__(self, raw=None, chain=None) -> None:
        self.raw_message = raw
        self.message = chain or []


class FakeApi:
    def __init__(self, payloads=None, history=None) -> None:
        self.payloads = payloads or {}
        self.history = list(history or [])
        self.sent = []
        self.history_calls = []

    async def call_action(self, action: str, **kwargs):
        # 私聊发出去就记下来
        if action == "send_private_msg":
            self.sent.append(kwargs)
            return {}
        # 按 ID 取原始消息
        if action == "get_msg":
            return self.payloads.get(str(kwargs.get("message_id")))
        # 不引用时按页拉群历史，列表从旧到新
        if action == "get_group_msg_history":
            self.history_calls.append(kwargs)
            seq = int(kwargs.get("message_seq") or 0)
            count = int(kwargs.get("count") or 20)
            if seq == 0:
                chunk = self.history[-count:]
            else:
                idx = next(
                    (
                        i
                        for i, msg in enumerate(self.history)
                        if str(msg.get("message_id")) == str(seq)
                    ),
                    -1,
                )
                # 游标之前没有更旧的了
                if idx <= 0:
                    chunk = []
                else:
                    chunk = self.history[max(0, idx - count) : idx]
            return {"messages": chunk}
        return None


class FakeBot:
    def __init__(self, payloads=None, history=None) -> None:
        self.api = FakeApi(payloads, history)


class FakeEvent:
    def __init__(
        self,
        admin: bool = True,
        sender: str = "10086",
        raw=None,
        chain=None,
        payloads=None,
        history=None,
        message_id: str = "100",
        has_obj: bool = True,
    ) -> None:
        self._admin = admin
        self.sender = sender
        self.message_id = message_id
        # 没有消息对象时抽不出引用
        if has_obj:
            self.message_obj = FakeMessage(raw=raw, chain=chain)
        else:
            self.message_obj = None
        self.bot = FakeBot(payloads, history)

    def is_admin(self) -> bool:
        return self._admin

    def get_sender_id(self) -> str:
        return self.sender

    def get_group_id(self) -> str:
        return "123"

    def get_message_id(self) -> str:
        return self.message_id


def _msg(
    mid: int,
    time: int,
    user_id: str = "9",
    nick: str = "别人",
    text: str = "",
    card_json: str = "",
) -> dict:
    if card_json:
        message = [{"type": "json", "data": {"data": card_json}}]
    else:
        message = [{"type": "text", "data": {"text": text}}]
    return {
        "message_id": mid,
        "time": time,
        "sender": {"user_id": user_id, "nickname": nick, "card": nick},
        "message": message,
        "raw_message": text,
    }


class DebugPayloadTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_is_rejected(self) -> None:
        event = FakeEvent(admin=False)
        text = await inspect_payload(event, "123", "11")
        self.assertEqual(text, REJECT_MESSAGE)
        self.assertEqual(event.bot.api.sent, [])

    async def test_previous_from_history(self) -> None:
        prev = _msg(11, 10, card_json='{"prompt":"卡片"}')
        event = FakeEvent(history=[prev, _msg(100, 20, text="查询")])
        text = await inspect_payload(event, "123", "")
        self.assertIn("已私聊发给你", text)
        body = event.bot.api.sent[0]["message"]
        self.assertIn("卡片", body)

    async def test_no_match_in_history(self) -> None:
        event = FakeEvent(history=[_msg(100, 20, text="查询")])
        text = await inspect_payload(event, "123", "")
        self.assertEqual(text, NO_MATCH)

    async def test_filter_by_nickname(self) -> None:
        target = _msg(11, 10, user_id="20001", nick="张三", card_json='{"prompt":"广告"}')
        other = _msg(12, 11, text="闲聊")
        event = FakeEvent(history=[target, other, _msg(100, 20, text="查询")])
        text = await inspect_payload(event, "123", "", sender="张三")
        body = event.bot.api.sent[0]["message"]
        self.assertIn("广告", body)
        self.assertIn("已私聊发给你", text)

    async def test_turns_page_when_first_misses(self) -> None:
        target = _msg(1, 1, user_id="20001", nick="张三", card_json='{"prompt":"旧卡片"}')
        others = [_msg(i, i, text="垫") for i in range(2, 22)]
        event = FakeEvent(history=[target, *others])
        text = await inspect_payload(event, "123", "", sender="张三")
        self.assertIn("已私聊发给你", text)
        self.assertGreaterEqual(len(event.bot.api.history_calls), 2)
        body = event.bot.api.sent[0]["message"]
        self.assertIn("旧卡片", body)

    async def test_reply_fetches_and_privates(self) -> None:
        payload = {
            "message_id": 11,
            "message": [
                {
                    "type": "json",
                    "data": {"data": '{"meta":{"news":{"title":"广告"}}}}'},
                }
            ],
        }
        event = FakeEvent(chain=[FakeReply("11")], payloads={"11": payload})
        text = await inspect_payload(event, "123", "")
        self.assertIn("已私聊发给你", text)
        self.assertEqual(len(event.bot.api.sent), 1)
        body = event.bot.api.sent[0]["message"]
        self.assertIn("广告", body)
        self.assertIn('"type": "json"', body)

    async def test_message_id_arg(self) -> None:
        event = FakeEvent(payloads={"22": {"message_id": 22, "raw_message": ""}})
        text = await inspect_payload(event, "123", "22")
        self.assertIn("已私聊发给你", text)

    async def test_missing_msg_is_not_found(self) -> None:
        event = FakeEvent()
        text = await inspect_payload(event, "123", "99")
        self.assertEqual(text, NOT_FOUND)

    def test_match_skips_current_and_needs_sender(self) -> None:
        current = _msg(100, 2, nick="张三")
        other = _msg(11, 1, nick="张三")
        self.assertFalse(match_message(current, "张三", "", "100"))
        self.assertTrue(match_message(other, "张三", "", "100"))
        self.assertFalse(match_message(other, "李四", "", "100"))

    def test_reply_from_raw_array(self) -> None:
        event = FakeEvent(
            raw={"message": [{"type": "reply", "data": {"id": "33"}}]}
        )
        self.assertEqual(reply_id_of(event), "33")

    def test_dump_keeps_inner_json_string(self) -> None:
        raw = {"data": '{"prompt":"[分享]"}'}
        text = dump_payload(raw)
        self.assertIn('\\"prompt\\"', text)
        self.assertEqual(to_plain("hi"), "hi")
