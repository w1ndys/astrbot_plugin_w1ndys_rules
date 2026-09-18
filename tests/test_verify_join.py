# 入群验证文案：关着不建码；开了写入 pending；机器人和空 QQ 跳过。提示要求私聊交码。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules._shared.group_switch_store import GroupSwitchStore
from astrbot_plugin_w1ndys_rules.business.verify_join import (
    hint_text,
    new_code,
    start_pending,
)
from astrbot_plugin_w1ndys_rules.data.verify_store import VerifyStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FEATURE_VERIFY,
    VERIFY_CODE_LEN,
)


class VerifyJoinTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.store = VerifyStore(db_path)
        self.switches = GroupSwitchStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_new_code_avoids_used(self) -> None:
        await self.store.put("123", "10001", "000000")
        code = new_code(self.store, "123")
        self.assertEqual(len(code), VERIFY_CODE_LEN)
        self.assertTrue(code.isdigit())
        self.assertNotEqual(code, "000000")

    def test_hint_contains_code(self) -> None:
        text = hint_text("123456")
        self.assertIn("123456", text)
        self.assertIn("私聊", text)

    async def test_off_does_not_register(self) -> None:
        text = await start_pending(self.store, self.switches, "123", "10001")
        self.assertEqual(text, "")
        self.assertEqual(self.store.get_code("123", "10001"), "")

    async def test_on_registers_and_hint_has_code(self) -> None:
        await self.switches.set_on("123", FEATURE_VERIFY, True)
        text = await start_pending(self.store, self.switches, "123", "10001")
        code = self.store.get_code("123", "10001")
        self.assertEqual(len(code), VERIFY_CODE_LEN)
        self.assertIn(code, text)
        self.assertEqual(text, hint_text(code))

    async def test_bot_self_is_skipped(self) -> None:
        await self.switches.set_on("123", FEATURE_VERIFY, True)
        text = await start_pending(
            self.store, self.switches, "123", "999", self_id="999"
        )
        self.assertEqual(text, "")
        self.assertEqual(self.store.get_code("123", "999"), "")

    async def test_empty_user_is_skipped(self) -> None:
        await self.switches.set_on("123", FEATURE_VERIFY, True)
        text = await start_pending(self.store, self.switches, "123", "")
        self.assertEqual(text, "")

    async def test_rejoin_overwrites(self) -> None:
        await self.switches.set_on("123", FEATURE_VERIFY, True)
        await start_pending(self.store, self.switches, "123", "10001")
        first = self.store.get_code("123", "10001")
        await start_pending(self.store, self.switches, "123", "10001")
        second = self.store.get_code("123", "10001")
        self.assertTrue(second)
        self.assertEqual(len(second), VERIFY_CODE_LEN)
        # 两次都成功写入；码可能碰巧相同，但 pending 仍在
        self.assertEqual(self.store.get_code("123", "10001"), second)
        self.assertTrue(first)
