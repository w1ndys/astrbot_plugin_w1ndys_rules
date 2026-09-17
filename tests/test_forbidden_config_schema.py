# WebUI 违禁配置：只保留单值字段，可重复数据必须进入 SQLite。

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ForbiddenConfigSchemaTest(unittest.TestCase):
    """验证 WebUI 不再承载触发词和违禁样本。"""

    def test_only_fixed_forbidden_fields_remain_in_webui(self) -> None:
        """触发词和样本移出 WebUI，其余固定字段继续保留。"""
        schema = json.loads((ROOT / "_conf_schema.json").read_text())

        self.assertNotIn("forbidden_trigger_words", schema)
        self.assertNotIn("forbidden_samples", schema)
        self.assertIn("forbidden_guideline", schema)
        self.assertIn("forbidden_mute_seconds", schema)
        self.assertIn("forbidden_remind_text", schema)
        self.assertIn("forbidden_feishu_webhook", schema)
