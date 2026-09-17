# 交码包含判定：前后不能是数字。未通过禁言秒数：默认 600，0 不禁，超过 30 天夹住。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.verify_check import code_in_text, mute_seconds
from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_VERIFY_MUTE_SECONDS,
    MAX_FORBIDDEN_MUTE_SECONDS,
    VERIFY_CFG_MUTE_SECONDS,
)


class VerifyCheckTest(unittest.TestCase):
    def test_plain_code_matches(self) -> None:
        self.assertTrue(code_in_text("123456", "123456"))

    def test_code_among_words_matches(self) -> None:
        self.assertTrue(code_in_text("请看123456谢谢", "123456"))
        self.assertTrue(code_in_text("验证码：123456", "123456"))

    def test_embedded_in_longer_number_does_not_match(self) -> None:
        self.assertFalse(code_in_text("123456789", "123456"))
        self.assertFalse(code_in_text("0123456", "123456"))
        self.assertFalse(code_in_text("x1234567", "123456"))

    def test_missing_or_empty_code_does_not_match(self) -> None:
        self.assertFalse(code_in_text("12345", "123456"))
        self.assertFalse(code_in_text("hello", "123456"))
        self.assertFalse(code_in_text("123456", ""))
        self.assertFalse(code_in_text("", "123456"))

    def test_mute_default_when_missing(self) -> None:
        self.assertEqual(mute_seconds(None), DEFAULT_VERIFY_MUTE_SECONDS)
        self.assertEqual(mute_seconds({}), DEFAULT_VERIFY_MUTE_SECONDS)
        self.assertEqual(
            mute_seconds({VERIFY_CFG_MUTE_SECONDS: ""}),
            DEFAULT_VERIFY_MUTE_SECONDS,
        )
        self.assertEqual(
            mute_seconds({VERIFY_CFG_MUTE_SECONDS: "abc"}),
            DEFAULT_VERIFY_MUTE_SECONDS,
        )

    def test_mute_zero_and_negative(self) -> None:
        self.assertEqual(mute_seconds({VERIFY_CFG_MUTE_SECONDS: "0"}), 0)
        self.assertEqual(mute_seconds({VERIFY_CFG_MUTE_SECONDS: "-1"}), 0)

    def test_mute_configured_and_clamped(self) -> None:
        self.assertEqual(mute_seconds({VERIFY_CFG_MUTE_SECONDS: "60"}), 60)
        self.assertEqual(
            mute_seconds({VERIFY_CFG_MUTE_SECONDS: "99999999"}),
            MAX_FORBIDDEN_MUTE_SECONDS,
        )
