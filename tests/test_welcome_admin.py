# 欢迎语文案：命令头剥离、权限、空文案关闭和超长拒绝。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.welcome_admin import (
    set_welcome,
    show_welcome,
    strip_set_header,
    usage_text,
)
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import WELCOME_MAX_LEN


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    """测试用的发言人。可模拟 AstrBot 管理员或本群角色。"""

    def __init__(self, admin: bool = False, role: str = "") -> None:
        self._admin = admin
        # 没有角色时不要伪造 sender，读不到就当普通群员
        if role:
            self.message_obj = FakeMessage({"sender": {"role": role}})
        else:
            self.message_obj = FakeMessage(None)

    def is_admin(self) -> bool:
        """当前发言人是不是 AstrBot 管理员。"""
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
        self.assertEqual(
            strip_set_header("欢迎语 设置\n欢迎入群~\n请看群规"),
            "欢迎入群~\n请看群规",
        )

    def test_strip_when_header_already_gone(self) -> None:
        self.assertEqual(strip_set_header("欢迎入群~"), "欢迎入群~")

    async def test_empty_payload_closes_group(self) -> None:
        text = await set_welcome(
            self.store, self.event, self.group_id, "欢迎语 设置"
        )
        self.assertIn("已关闭", text)
        self.assertEqual(self.store.get_content(self.group_id), "")

    async def test_stranger_is_silent(self) -> None:
        text = await set_welcome(
            self.store,
            FakeEvent(admin=False),
            self.group_id,
            "欢迎语 设置 欢迎入群~",
        )
        self.assertEqual(text, "")
        self.assertIsNone(self.store.get_content(self.group_id))

    async def test_qq_owner_can_set(self) -> None:
        text = await set_welcome(
            self.store,
            FakeEvent(admin=False, role="owner"),
            self.group_id,
            "欢迎语 设置 群主写的",
        )
        self.assertIn("群主写的", text)
        self.assertEqual(self.store.get_content(self.group_id), "群主写的")

    async def test_too_long_writes_nothing(self) -> None:
        payload = "欢迎语 设置 " + "哈" * (WELCOME_MAX_LEN + 1)
        text = await set_welcome(self.store, self.event, self.group_id, payload)
        self.assertIn("最多", text)
        self.assertIsNone(self.store.get_content(self.group_id))

    async def test_show_when_missing(self) -> None:
        text = show_welcome(self.store, self.event, self.group_id)
        self.assertIn("还没有单独设置欢迎语", text)
        self.assertIn("欢迎语 设置", text)
        self.assertIn(usage_text()[:4], text)
