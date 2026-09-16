# 违禁词触发匹配：包含即可，英文不区分大小写，不进模型。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_match import (
    find_trigger,
    parse_trigger_words,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_TRIGGER_WORDS,
)


class ForbiddenMatchTest(unittest.TestCase):
    def test_config_key_matches_schema(self) -> None:
        self.assertEqual(FORBIDDEN_CFG_TRIGGER_WORDS, "forbidden_trigger_words")

    def test_parse_skips_blank_lines(self) -> None:
        words = parse_trigger_words("  广告  \n\nFreeNitro\n")
        self.assertEqual(words, ["广告", "FreeNitro"])

    def test_parse_empty(self) -> None:
        self.assertEqual(parse_trigger_words(""), [])
        self.assertEqual(parse_trigger_words("   \n  "), [])

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
