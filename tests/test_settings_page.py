# WebUI 全局配置：校验后写进 SettingStore。schema 只在空表时导入一次。

import sys
import tempfile
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
from astrbot_plugin_w1ndys_rules.data.setting_store import SettingStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_URL,
)


class SettingsPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "rules.db"
        self.store = SettingStore(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_get_includes_webhook(self) -> None:
        config = {
            CFG_FORBIDDEN_GROUPS: ["123"],
            FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://example.com/hook",
            FORBIDDEN_CFG_MUTE_SECONDS: 60,
        }
        data = get_settings(config)
        self.assertEqual(data[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertEqual(data[FORBIDDEN_CFG_FEISHU_WEBHOOK], "https://example.com/hook")

    def test_import_fills_all_keys(self) -> None:
        """空表导入后 18 个键都有行，不再回退读 schema。"""
        self.store.import_if_empty({"x": 1})
        self.assertEqual(self.store.count(), 18)
        data = self.store.load_dict()
        self.assertEqual(data[CFG_FORBIDDEN_GROUPS], [])
        self.assertEqual(data[FORBIDDEN_CFG_FEISHU_WEBHOOK], "")
        self.assertEqual(data[FORBIDDEN_CFG_MUTE_SECONDS], 0)
        self.assertFalse(data[FORBIDDEN_CFG_TRIGGER_URL])

    async def test_save_writes_store(self) -> None:
        ok, message = await save_settings(
            self.store,
            {
                CFG_FORBIDDEN_GROUPS: ["123"],
                FORBIDDEN_CFG_FEISHU_WEBHOOK: "https://new.example/hook",
                FORBIDDEN_CFG_MUTE_SECONDS: 90,
            },
        )
        self.assertTrue(ok)
        self.assertIn("保存", message)
        data = self.store.load_dict()
        self.assertEqual(data[CFG_FORBIDDEN_GROUPS], ["123"])
        self.assertEqual(data[FORBIDDEN_CFG_MUTE_SECONDS], 90)
        self.assertEqual(data[FORBIDDEN_CFG_FEISHU_WEBHOOK], "https://new.example/hook")

    async def test_save_keeps_keys_not_sent(self) -> None:
        """没带的键不覆盖库里已有的值。"""
        await self.store.set_value(FORBIDDEN_CFG_MUTE_SECONDS, 90)
        ok, _message = await save_settings(
            self.store, {FORBIDDEN_CFG_TRIGGER_URL: True}
        )
        self.assertTrue(ok)
        data = self.store.load_dict()
        self.assertEqual(data[FORBIDDEN_CFG_MUTE_SECONDS], 90)
        self.assertTrue(data[FORBIDDEN_CFG_TRIGGER_URL])

    async def test_save_rejects_bad_seconds(self) -> None:
        ok, message = await save_settings(
            self.store, {FORBIDDEN_CFG_MUTE_SECONDS: "abc"}
        )
        self.assertFalse(ok)
        self.assertIn("整数", message)
        self.assertEqual(self.store.load_dict()[FORBIDDEN_CFG_MUTE_SECONDS], 0)

    async def test_save_bool_flags(self) -> None:
        """规则开关能读写，假值当关。"""
        ok, _message = await save_settings(
            self.store,
            {
                FORBIDDEN_CFG_TRIGGER_URL: True,
                FORBIDDEN_CFG_TRIGGER_QQ: False,
            },
        )
        self.assertTrue(ok)
        data = self.store.load_dict()
        self.assertTrue(data[FORBIDDEN_CFG_TRIGGER_URL])
        self.assertFalse(data[FORBIDDEN_CFG_TRIGGER_QQ])

    async def test_import_does_not_overwrite(self) -> None:
        """表里已经有行时导入不覆盖，改传别的 dict 也不动。"""
        await self.store.set_value(FORBIDDEN_CFG_MUTE_SECONDS, 90)
        self.store.import_if_empty({FORBIDDEN_CFG_MUTE_SECONDS: 30})
        self.assertEqual(self.store.load_dict()[FORBIDDEN_CFG_MUTE_SECONDS], 90)

    async def test_import_only_once(self) -> None:
        """空表导入后改传入 dict，不再导入，库值不变。"""
        self.store.import_if_empty({FORBIDDEN_CFG_MUTE_SECONDS: 30})
        self.store.import_if_empty({FORBIDDEN_CFG_MUTE_SECONDS: 99})
        data = self.store.load_dict()
        self.assertEqual(data[FORBIDDEN_CFG_MUTE_SECONDS], 30)
        self.assertEqual(self.store.count(), 18)
