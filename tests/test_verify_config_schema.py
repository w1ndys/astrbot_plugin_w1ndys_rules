# WebUI 入群验证：只放未通过禁言秒数，不另开页面。

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_VERIFY_MUTE_SECONDS,
    VERIFY_CFG_MUTE_SECONDS,
)


class VerifyConfigSchemaTest(unittest.TestCase):
    """验证 WebUI 里入群验证禁言秒数字段。"""

    def test_mute_seconds_is_int_with_default(self) -> None:
        schema = json.loads((ROOT / "_conf_schema.json").read_text())
        field = schema[VERIFY_CFG_MUTE_SECONDS]
        self.assertEqual(field["type"], "int")
        self.assertEqual(field["default"], DEFAULT_VERIFY_MUTE_SECONDS)
