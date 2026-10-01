# WebUI 全局配置：Pages 读写全部 schema 字段，含飞书 webhook。


import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.settings_page import (
    get_settings,
    save_settings,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_URL,
)



class FakeConfig(dict):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.saved = 0

    def save_config(self) -> None:
        self.saved += 1


class SettingsPageTest(unittest.TestCase):
    def test_get_includes_webhook(self) -> None:
        config = {
            CFG_FORBIDDEN_GROUPS: ["123"],
            FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://example.com/hook",
            FORBIDDEN_CFG_MUTE_SECONDS: 60,
        }
        data = get_settings(config)
        self.assertEqual(data[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertEqual(data[FORBIDDEN_CFG_FEISHU_WEBHOOK], "https://example.com/hook")

    def test_save_writes_webhook(self) -> None:
        config = FakeConfig(
            {
                FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://old.example/hook",
                FORBIDDEN_CFG_MUTE_SECONDS: 60,
            }
        )
        ok, message = save_settings(
            config,
            {
                CFG_FORBIDDEN_GROUPS: ["123"],
                FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://new.example/hook",
                FORBIDDEN_CFG_MUTE_SECONDS: 90,
            },
        )
        self.assertTrue(ok)
        self.assertIn("保存", message)
        self.assertEqual(config[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertEqual(config[FORBIDDEN_CFG_MUTE_SECONDS], 90)
        self.assertEqual(config[FORBIDDEN_CFG_FEISHU_WEBHOOK], "https://new.example/hook")
        self.assertEqual(config.saved, 1)


    def test_save_rejects_bad_seconds(self) -> None:
        config = FakeConfig({FORBIDDEN_CFG_MUTE_SECONDS: 60})
        ok, message = save_settings(config, {FORBIDDEN_CFG_MUTE_SECONDS: "abc"})
        self.assertFalse(ok)
        self.assertIn("整数", message)
        self.assertEqual(config[FORBIDDEN_CFG_MUTE_SECONDS], 60)

    def test_save_bool_flags(self) -> None:
        """规则开关能读写，假值当关。"""
        config = FakeConfig()
        ok, _message = save_settings(config, {FORBIDDEN_CFG_TRIGGER_URL: True})
        self.assertTrue(ok)
        data = get_settings(config)
        self.assertTrue(data[FORBIDDEN_CFG_TRIGGER_URL])
        self.assertFalse(data[FORBIDDEN_CFG_TRIGGER_QQ])

