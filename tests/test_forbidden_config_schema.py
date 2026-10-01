# WebUI 违禁配置：准则单行、样本多行，触发词不进 WebUI。

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ForbiddenConfigSchemaTest(unittest.TestCase):
    """验证字段类型，以及官方页全部隐藏。"""

    def test_samples_are_multiline_and_official_page_hidden(self) -> None:
        """样本用 text 多行框，准则保持 string，官方页全部 invisible。"""
        schema = json.loads((ROOT / "_conf_schema.json").read_text())

        self.assertNotIn("forbidden_trigger_words", schema)
        self.assertEqual(schema["forbidden_guideline"]["type"], "string")
        self.assertEqual(schema["forbidden_samples"]["type"], "text")
        self.assertIn("forbidden_mute_seconds", schema)
        self.assertIn("forbidden_remind_text", schema)
        self.assertIn("forbidden_feishu_webhook", schema)
        self.assertTrue(schema["forbidden_feishu_webhook"]["secret"])
        self.assertEqual(schema["forbidden_block_group_card_groups"]["type"], "list")
        self.assertEqual(schema["forbidden_block_group_card_groups"]["default"], [])
        self.assertEqual(
            schema["forbidden_block_group_card_groups"]["items"], {"type": "string"}
        )
        for key in (
            "forbidden_trigger_url",
            "forbidden_trigger_group",
            "forbidden_trigger_qq",
            "forbidden_trigger_phone",
            "forbidden_trigger_wechat",
        ):
            # 规则触发默认关，避免一装插件就扫所有数字
            self.assertEqual(schema[key]["type"], "bool")
            self.assertIs(schema[key]["default"], False)

        for key in (
            "keyword_groups",
            "forbidden_groups",
            "welcome_groups",
            "verify_groups",
            "invite_groups",
        ):
            # 功能开关全部是群号名单，空名单即关
            self.assertEqual(schema[key]["type"], "list")
            self.assertEqual(schema[key]["default"], [])
            self.assertEqual(schema[key]["items"], {"type": "string"})

        self.assertEqual(schema["welcome_text"]["type"], "text")
        self.assertEqual(schema["welcome_text"]["default"], "")
        for key, item in schema.items():
            # 官方插件配置页不展示任何字段，只在 Pages 改
            self.assertIs(item["invisible"], True, key)


