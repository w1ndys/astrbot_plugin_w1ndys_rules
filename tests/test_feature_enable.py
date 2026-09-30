# WebUI 群号名单：空名单即关，只认列表，空白项丢掉。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.feature_enable import (
    config_group_ids,
    feature_on,
)
from astrbot_plugin_w1ndys_rules.entity.constants import CFG_KEYWORD_GROUPS


class FeatureEnableTest(unittest.TestCase):
    def test_empty_and_missing_are_off(self) -> None:
        self.assertFalse(feature_on(None, CFG_KEYWORD_GROUPS, "123"))
        self.assertFalse(feature_on({}, CFG_KEYWORD_GROUPS, "123"))
        self.assertFalse(feature_on({CFG_KEYWORD_GROUPS: []}, CFG_KEYWORD_GROUPS, "123"))

    def test_listed_group_is_on(self) -> None:
        config = {CFG_KEYWORD_GROUPS: ["123", " 456 "]}
        self.assertTrue(feature_on(config, CFG_KEYWORD_GROUPS, "123"))
        self.assertTrue(feature_on(config, CFG_KEYWORD_GROUPS, "456"))
        self.assertFalse(feature_on(config, CFG_KEYWORD_GROUPS, "789"))

    def test_blank_items_and_old_text_are_ignored(self) -> None:
        self.assertEqual(
            config_group_ids({CFG_KEYWORD_GROUPS: ["", " 123 ", ""]}, CFG_KEYWORD_GROUPS),
            ["123"],
        )
        # 旧文本框不再拆成名单，避免误开
        self.assertEqual(
            config_group_ids({CFG_KEYWORD_GROUPS: "123"}, CFG_KEYWORD_GROUPS),
            [],
        )

    def test_empty_group_id_is_off(self) -> None:
        config = {CFG_KEYWORD_GROUPS: ["123"]}
        self.assertFalse(feature_on(config, CFG_KEYWORD_GROUPS, ""))
