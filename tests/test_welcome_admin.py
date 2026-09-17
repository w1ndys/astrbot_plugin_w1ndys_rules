# 欢迎语文案：只测命令头剥离、权限、空文案和超长拒绝。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.welcome_admin import (
    REJECT_MESSAGE,
    set_welcome,
    show_welcome,
    strip_set_header,
    usage_text,
)
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import WELCOME_MAX_LEN


class FakeEvent:
    """测试用的发言人。只提供 is_admin。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        """当前发言人是不是管理员。"""
        return self._admin


class WelcomeAdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = WelcomeStore(Path(self._tmp.name) / "rules.db")
        self.event = FakeEvent(admin=True)
        self.group_id = "123456"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strip_same_line_and_next_line(self) -> None:
        self.assertEqual(strip_set_header("欢迎语 设置 欢迎入群~"), "欢迎入群~")
        self.assertEqual(strip_set_header("欢迎语 设置\n欢迎入群~\n请看群规"), "欢迎入群~\n请看群规")

    def test_strip_when_header_already_gone(self) -> None:
        self.assertEqual(strip_set_header("欢迎入群~"), "欢迎入群~")

    async def test_empty_payload_returns_usage(self) -> None:
        text = await set_welcome(
            self.store, self.event, self.group_id, "欢迎语 设置"
        )
        self.assertEqual(text, usage_text())
        self.assertEqual(self.store.get_content(self.group_id), "")

    async def test_non_admin_is_rejected(self) -> None:
        text = await set_welcome(
            self.store,
            FakeEvent(admin=False),
            self.group_id,
            "欢迎语 设置 欢迎入群~",
        )
        self.assertEqual(text, REJECT_MESSAGE)
        self.assertEqual(self.store.get_content(self.group_id), "")

    async def test_too_long_writes_nothing(self) -> None:
        payload = "欢迎语 设置 " + "哈" * (WELCOME_MAX_LEN + 1)
        text = await set_welcome(self.store, self.event, self.group_id, payload)
        self.assertIn("最多", text)
        self.assertEqual(self.store.get_content(self.group_id), "")

    async def test_show_when_missing(self) -> None:
        text = show_welcome(self.store, self.event, self.group_id)
        self.assertIn("还没有设置欢迎语", text)
        self.assertIn("欢迎语 设置", text)
