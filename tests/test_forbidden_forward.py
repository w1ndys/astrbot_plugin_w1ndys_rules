# 业务层：合并转发从原始 payload.message 抽正文。
# 本层 message 只含一层记录；嵌套转发按 id 递归 get_forward_msg。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_forward import (
    collect_forward_text,
    message_audit_text,
    resolve_audit_text,
)


class FakeMessage:
    def __init__(self, raw) -> None:
        """挂上原始 payload。"""
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw) -> None:
        """只带 message_obj。"""
        self.message_obj = FakeMessage(raw)


class ForwardTextTest(unittest.TestCase):
    def test_placeholder_uses_node_message(self) -> None:
        """message 直接是节点列表，占位符换成内层字。"""
        event = FakeEvent(
            {
                "message": [
                    {
                        "sender": {"nickname": "甲"},
                        "message": [
                            {"type": "text", "data": {"text": "加群 123456"}},
                        ],
                    }
                ]
            }
        )
        text = message_audit_text(event, "[转发消息]")
        self.assertEqual(text, "加群 123456")

    def test_forward_seg_content(self) -> None:
        """forward 段 data.content 里的节点。"""
        event = FakeEvent(
            {
                "message": [
                    {
                        "type": "forward",
                        "data": {
                            "id": "abc",
                            "content": [
                                {
                                    "type": "node",
                                    "data": {
                                        "content": [
                                            {"type": "text", "data": {"text": "广告链接"}},
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        )
        self.assertEqual(collect_forward_text(event), "广告链接")

    def test_plain_text_unchanged(self) -> None:
        """普通消息不改。"""
        event = FakeEvent(
            {"message": [{"type": "text", "data": {"text": "今天天气"}}]}
        )
        self.assertEqual(message_audit_text(event, "今天天气"), "今天天气")
        self.assertEqual(collect_forward_text(event), "")

    def test_nested_forward_events(self) -> None:

        """外层 forward.content 里还是完整事件，事件 message 再套 forward。"""
        event = FakeEvent(
            {
                "message": [
                    {
                        "type": "forward",
                        "data": {
                            "id": "7691653435027338745",
                            "content": [
                                {
                                    "user_id": 1094950020,
                                    "message": [
                                        {
                                            "type": "forward",
                                            "data": {
                                                "id": "7691653435027338752",
                                                "content": [
                                                    {
                                                        "user_id": 1,
                                                        "message": [
                                                            {
                                                                "type": "text",
                                                                "data": {
                                                                    "text": "这是一条违规的合并转发"
                                                                },
                                                            }
                                                        ],
                                                    }
                                                ],
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ]
            }
        )
        text = message_audit_text(event, "[转发消息]")
        self.assertEqual(text, "这是一条违规的合并转发")



class FakeApi:
    def __init__(self, payload) -> None:
        """记下调用，并回固定转发包。"""
        self.payload = payload
        self.calls = []

    async def call_action(self, action: str, **kwargs):
        """只认 get_forward_msg。"""
        self.calls.append((action, kwargs))
        # 别的动作没有包
        if action != "get_forward_msg":
            return None
        return self.payload


class FetchEvent(FakeEvent):
    def __init__(self, raw, payload) -> None:
        """带 bot，方便拉 get_forward_msg。"""
        super().__init__(raw)
        self.bot = type("Bot", (), {"api": FakeApi(payload)})()


class ForwardFetchTest(unittest.IsolatedAsyncioTestCase):
    async def test_id_only_fetches_nodes(self) -> None:
        """payload 只有 id 时按 get_forward_msg 抽字。"""
        event = FetchEvent(
            {"message": [{"type": "forward", "data": {"id": "fwd_1"}}]},
            {
                "messages": [
                    {
                        "message": [
                            {"type": "text", "data": {"text": "加微信 abc12xyz"}},
                        ]
                    }
                ]
            },
        )
        text = await resolve_audit_text(event, "[转发消息]")
        self.assertEqual(text, "加微信 abc12xyz")
        self.assertEqual(event.bot.api.calls[0][0], "get_forward_msg")

    async def test_embedded_skips_fetch(self) -> None:
        """已经有节点就不再打协议。"""
        event = FetchEvent(
            {
                "message": [
                    {
                        "type": "forward",
                        "data": {
                            "id": "fwd_1",
                            "content": [
                                {
                                    "message": [
                                        {"type": "text", "data": {"text": "广告链接"}},
                                    ]
                                }
                            ],
                        },
                    }
                ]
            },
            {"messages": []},
        )
        text = await resolve_audit_text(event, "[转发消息]")
        self.assertEqual(text, "广告链接")
        self.assertEqual(event.bot.api.calls, [])

    async def test_no_bot_keeps_placeholder(self) -> None:
        """没有 bot 时占位符原样留下。"""
        event = FakeEvent(
            {"message": [{"type": "forward", "data": {"id": "fwd_1"}}]}
        )
        text = await resolve_audit_text(event, "[转发消息]")
        self.assertEqual(text, "[转发消息]")

    async def test_nested_id_in_first_layer_is_fetched(self) -> None:
        """本层 message 有记录，嵌套 forward 只有 id，要再拉一层。"""
        event = FetchEvent(
            {
                "message": [
                    {
                        "sender": {"nickname": "甲"},
                        "message": [
                            {"type": "text", "data": {"text": "外层招呼"}},
                            {"type": "forward", "data": {"id": "fwd_2"}},
                        ],
                    }
                ]
            },
            {
                "messages": [
                    {
                        "message": [
                            {"type": "text", "data": {"text": "内层广告"}},
                        ]
                    }
                ]
            },
        )
        text = await resolve_audit_text(event, "[转发消息]")
        self.assertEqual(text, "外层招呼\n内层广告")
        self.assertEqual(event.bot.api.calls[0][1].get("id"), "fwd_2")
