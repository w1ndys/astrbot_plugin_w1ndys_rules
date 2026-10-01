# 业务层：合并转发从原始 payload.message 抽正文。

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

