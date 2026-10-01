# 违禁词触发匹配：包含即可，英文不区分大小写，不进模型。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_match import (
    find_pattern_trigger,
    find_trigger,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_TRIGGER_GROUP,
    FORBIDDEN_CFG_TRIGGER_PHONE,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_URL,
    FORBIDDEN_CFG_TRIGGER_WECHAT,
    FORBIDDEN_PATTERN_GROUP,
    FORBIDDEN_PATTERN_PHONE,
    FORBIDDEN_PATTERN_QQ,
    FORBIDDEN_PATTERN_URL,
    FORBIDDEN_PATTERN_WECHAT,
)


class ForbiddenMatchTest(unittest.TestCase):
    def test_chinese_contains(self) -> None:
        hit = find_trigger("大家来看这个广告链接", ["广告", "加群"])
        self.assertEqual(hit, "广告")

    def test_english_case_insensitive(self) -> None:
        hit = find_trigger("click FREENITRO now", ["FreeNitro"])
        self.assertEqual(hit, "FreeNitro")

    def test_first_word_wins(self) -> None:
        hit = find_trigger("广告加群", ["加群", "广告"])
        self.assertEqual(hit, "加群")

    def test_no_match(self) -> None:
        self.assertEqual(find_trigger("今天天气不错", ["广告"]), "")

    def test_empty_message_or_words(self) -> None:
        self.assertEqual(find_trigger("", ["广告"]), "")
        self.assertEqual(find_trigger("广告", []), "")


class PatternTriggerTest(unittest.TestCase):
    def test_off_by_default(self) -> None:
        """开关关着时网址也不当触发词。"""
        self.assertEqual(find_pattern_trigger("https://a.com 加群", {}), "")

    def test_url_phone_wechat_group_qq(self) -> None:
        """五个开关各自命中。"""
        self.assertEqual(
            find_pattern_trigger("看 https://a.com", {FORBIDDEN_CFG_TRIGGER_URL: True}),
            FORBIDDEN_PATTERN_URL,
        )
        self.assertEqual(
            find_pattern_trigger("加我 13800138000", {FORBIDDEN_CFG_TRIGGER_PHONE: True}),
            FORBIDDEN_PATTERN_PHONE,
        )
        self.assertEqual(
            find_pattern_trigger("微信 abcdefg1", {FORBIDDEN_CFG_TRIGGER_WECHAT: True}),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(
            find_pattern_trigger("加群 123456", {FORBIDDEN_CFG_TRIGGER_GROUP: True}),
            FORBIDDEN_PATTERN_GROUP,
        )
        self.assertEqual(
            find_pattern_trigger("私聊 10086", {FORBIDDEN_CFG_TRIGGER_QQ: True}),
            FORBIDDEN_PATTERN_QQ,
        )

    def test_qq_skips_phone_and_date(self) -> None:
        """手机号和 20 开头 8 位日期不当 QQ。"""
        self.assertEqual(
            find_pattern_trigger("13800138000", {FORBIDDEN_CFG_TRIGGER_QQ: True}),
            "",
        )
        self.assertEqual(
            find_pattern_trigger("20260330", {FORBIDDEN_CFG_TRIGGER_QQ: True}),
            "",
        )


    def test_wechat_hint_phrases(self) -> None:
        """口令扩到加微信/加v/vx/薇信，纯字母账号也认。"""
        cfg = {FORBIDDEN_CFG_TRIGGER_WECHAT: True}
        self.assertEqual(
            find_pattern_trigger("加微信 hellohello", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(
            find_pattern_trigger("加v abcdef", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(
            find_pattern_trigger("vx: abcdef", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(
            find_pattern_trigger("薇信 abcdef", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(
            find_pattern_trigger("wxid_abc123", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )

    def test_wechat_bare_mixed_not_english(self) -> None:
        """无口令只认字母数字都有的 6～20 位，纯英文和网址不送。"""
        cfg = {FORBIDDEN_CFG_TRIGGER_WECHAT: True}
        self.assertEqual(
            find_pattern_trigger("私聊 abc12xyz", cfg),
            FORBIDDEN_PATTERN_WECHAT,
        )
        self.assertEqual(find_pattern_trigger("今天 hellohello", cfg), "")
        self.assertEqual(find_pattern_trigger("看 example.com", cfg), "")
