# WebUI 违禁配置：准则单行、样本多行，触发词不进 WebUI。

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ForbiddenConfigSchemaTest(unittest.TestCase):
    """验证 WebUI 字段类型和职责划分。"""

    def test_samples_are_multiline_and_triggers_stay_out(self) -> None:
        """样本用 text 多行框，准则保持 string，触发词不出现在 schema。"""
        schema = json.loads((ROOT / "_conf_schema.json").read_text())

        self.assertNotIn("forbidden_trigger_words", schema)
        self.assertEqual(schema["forbidden_guideline"]["type"], "string")
        self.assertEqual(schema["forbidden_samples"]["type"], "text")
        self.assertIn("forbidden_mute_seconds", schema)
        self.assertIn("forbidden_remind_text", schema)
        self.assertIn("forbidden_feishu_webhook", schema)
