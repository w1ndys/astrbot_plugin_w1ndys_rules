# 业务层：违禁命中后拉最近 30 条，只撤回该用户的消息。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_action import (
    apply_hit_actions,
    history_messages,
    user_history_ids,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_RECALL_HISTORY_COUNT,
    FORBIDDEN_REASON_MODEL,
)


def _hist_msg(mid, user_id: str) -> dict:
    """拼一条历史消息。"""
    return {
        "message_id": mid,
        "sender": {"user_id": user_id},
    }


class FakeApi:
    """记录 OneBot 调用，并可塞进一页历史。"""

    def __init__(self, history=None) -> None:
        """可注入历史消息。"""
        self.calls = []
        self.history = list(history or [])


    async def call_action(self, action: str, **kwargs):
        """记下调用；拉历史时回注入的列表。"""
        self.calls.append((action, kwargs))
        # 命中后要拉最近一页
        if action == "get_group_msg_history":
            return {"messages": self.history}
        return {}


class FakeBot:
    """挂上 FakeApi。"""

    def __init__(self, history=None) -> None:
        """把历史交给 api。"""
        self.api = FakeApi(history)


class FakeMessage:
    """只带消息 ID。"""

    def __init__(self, message_id=123) -> None:
        """记下当前条 ID。"""
        self.message_id = message_id


class FakeEvent:
    """违禁处置用的假事件。"""

    def __init__(self, sender: str = "10001", self_id: str = "999", mid=123, history=None) -> None:
        """默认发言人不是机器人。"""
        self.bot = FakeBot(history)
        self._sender = sender
        self._self_id = self_id
        self.message_obj = FakeMessage(mid)

    def get_sender_id(self) -> str:
        """发言人 QQ。"""
        return self._sender

    def get_self_id(self) -> str:
        """机器人 QQ。"""
        return self._self_id



class HistoryParseTest(unittest.TestCase):
    def test_messages_field(self) -> None:
        """标准 {messages: [...]}。"""
        self.assertEqual(history_messages({"messages": [1, 2]}), [1, 2])

    def test_list_body(self) -> None:
        """有的实现直接回列表。"""
        self.assertEqual(history_messages([1]), [1])

    def test_user_ids_skip_others_and_dup(self) -> None:
        """只收这个人的 ID，重复的丢掉。"""
        raw = {
            "messages": [
                _hist_msg(1, "10001"),
                _hist_msg(2, "20002"),
                _hist_msg(1, "10001"),
                _hist_msg("x", "10001"),
            ]
        }
        self.assertEqual(user_history_ids(raw, "10001"), [1])


class RecallRecentTest(unittest.IsolatedAsyncioTestCase):
    async def test_recalls_only_this_user_not_current(self) -> None:
        """近 30 条里只撤该用户，当前条不删第二次，别人的不碰。"""
        history = [
            _hist_msg(10, "10001"),
            _hist_msg(11, "20002"),
            _hist_msg(123, "10001"),
            _hist_msg(12, "10001"),
        ]
        event = FakeEvent(history=history)
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0},
            "123",
            "广告",
            "这里有广告",
            reason_code=FORBIDDEN_REASON_MODEL,
        )
        calls = event.bot.api.calls
        self.assertEqual(calls[0], ("delete_msg", {"message_id": 123}))
        hist = calls[1]
        self.assertEqual(hist[0], "get_group_msg_history")
        self.assertEqual(hist[1]["group_id"], 123)
        self.assertEqual(hist[1]["count"], FORBIDDEN_RECALL_HISTORY_COUNT)
        self.assertEqual(hist[1]["message_seq"], 0)
        deleted = [kwargs["message_id"] for name, kwargs in calls if name == "delete_msg"]
        self.assertEqual(deleted, [123, 10, 12])

    async def test_skip_bot_self(self) -> None:
        """机器人自己不拉历史。"""
        event = FakeEvent(sender="999", self_id="999", history=[_hist_msg(10, "999")])
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0},
            "123",
            "广告",
            "这里有广告",
            reason_code=FORBIDDEN_REASON_MODEL,
        )
        names = [name for name, _kwargs in event.bot.api.calls]
        self.assertEqual(names, ["delete_msg"])
