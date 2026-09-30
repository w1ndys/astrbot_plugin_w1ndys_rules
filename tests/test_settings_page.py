# WebUI 全局配置：只读写非密钥字段，webhook 不进页面。

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
)


class FakeConfig(dict):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.saved = 0

    def save_config(self) -> None:
        self.saved += 1


class SettingsPageTest(unittest.TestCase):
    def test_get_omits_webhook(self) -> None:
        config = {
            CFG_FORBIDDEN_GROUPS: ["123"],
            FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://example.com/hook",
            FORBIDDEN_CFG_MUTE_SECONDS: 60,
        }
        data = get_settings(config)
        self.assertEqual(data[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertNotIn(FORBIDDEN_CFG_FEISHU_WEBHOOK, data)

    def test_save_ignores_webhook(self) -> None:
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
                FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://evil.example/hook",
                FORBIDDEN_CFG_MUTE_SECONDS: 90,
            },
        )
        self.assertTrue(ok)
        self.assertIn("保存", message)
        self.assertEqual(config[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertEqual(config[FORBIDDEN_CFG_MUTE_SECONDS], 90)
        self.assertEqual(config[FORBIDDEN_CFG_FEISHU_WEBHOOK], "https://old.example/hook")
        self.assertEqual(config.saved, 1)

    def test_save_rejects_bad_seconds(self) -> None:
        config = FakeConfig({FORBIDDEN_CFG_MUTE_SECONDS: 60})
        ok, message = save_settings(config, {FORBIDDEN_CFG_MUTE_SECONDS: "abc"})
        self.assertFalse(ok)
        self.assertIn("整数", message)
        self.assertEqual(config[FORBIDDEN_CFG_MUTE_SECONDS], 60)
