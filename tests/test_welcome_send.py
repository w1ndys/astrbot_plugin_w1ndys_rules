# 入群欢迎：名单外不发；独立空串关闭；没独立文案用全局或默认句。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.welcome_send import (
    is_group_increase,
    pick_welcome,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_WELCOME_GROUPS,
    CFG_WELCOME_TEXT,
    DEFAULT_WELCOME_TEXT,
    WELCOME_MAX_LEN,
)


class FakeWelcome:
    """测试替身：固定返回本群独立配置。"""

    def __init__(self, content: str | None = None) -> None:
        self.content = content

    def get_content(self, group_id: str) -> str | None:
        """返回构造时写入的独立配置。"""
        return self.content


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有消息对象时不是入群通知
        if has_obj:
            self.message_obj = FakeMessage(raw)
        else:
            self.message_obj = None


class WelcomeSendTest(unittest.TestCase):
    def test_notice_is_group_increase(self) -> None:
        event = FakeEvent({"notice_type": "group_increase", "user_id": "10001"})
        self.assertTrue(is_group_increase(event))

    def test_plain_message_is_not_increase(self) -> None:
        event = FakeEvent({"post_type": "message"})
        self.assertFalse(is_group_increase(event))
        self.assertFalse(is_group_increase(FakeEvent(has_obj=False)))

    def test_off_sends_nothing(self) -> None:
        config = {CFG_WELCOME_TEXT: "请先看群规"}
        self.assertEqual(pick_welcome(FakeWelcome(), config, "123"), "")

    def test_on_without_text_uses_default(self) -> None:
        config = {CFG_WELCOME_GROUPS: ["123"]}
        self.assertEqual(
            pick_welcome(FakeWelcome(), config, "123"), DEFAULT_WELCOME_TEXT
        )

    def test_on_uses_webui_text(self) -> None:
        config = {CFG_WELCOME_GROUPS: ["123"], CFG_WELCOME_TEXT: "请先看群规"}
        self.assertEqual(pick_welcome(FakeWelcome(), config, "123"), "请先看群规")

    def test_group_override_beats_global(self) -> None:
        config = {CFG_WELCOME_GROUPS: ["123"], CFG_WELCOME_TEXT: "全局句"}
        self.assertEqual(
            pick_welcome(FakeWelcome("本群句"), config, "123"), "本群句"
        )

    def test_empty_override_closes_even_if_on(self) -> None:
        config = {CFG_WELCOME_GROUPS: ["123"], CFG_WELCOME_TEXT: "全局句"}
        self.assertEqual(pick_welcome(FakeWelcome(""), config, "123"), "")

    def test_too_long_is_clipped(self) -> None:
        config = {
            CFG_WELCOME_GROUPS: ["123"],
            CFG_WELCOME_TEXT: "哈" * (WELCOME_MAX_LEN + 8),
        }
        text = pick_welcome(FakeWelcome(), config, "123")
        self.assertEqual(len(text), WELCOME_MAX_LEN)
