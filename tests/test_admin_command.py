# 管理命令：欢迎语设/查仍认；功能开/关和关键词批量不再认。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.admin_command import (
    handle_admin_command,
    parse_admin_command,
)
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    """测试用的发言人。只提供 is_admin 和可选群角色。"""

    def __init__(self, admin: bool = True, role: str = "") -> None:
        self._admin = admin
        # 没有角色时读不到 sender，当普通群员
        if role:
            self.message_obj = FakeMessage({"sender": {"role": role}})
        else:
            self.message_obj = FakeMessage(None)

    def is_admin(self) -> bool:
        """当前发言人是不是 AstrBot 管理员。"""
        return self._admin


class AdminCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.welcome = WelcomeStore(db_path)
        self.group_id = "123456"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_switch_phrases_are_not_commands(self) -> None:
        """群里发开/关不再当管理命令。"""
        self.assertEqual(parse_admin_command("关键词 开"), "")
        self.assertEqual(parse_admin_command("欢迎语 开"), "")

    def test_parse_welcome_headers(self) -> None:
        self.assertEqual(parse_admin_command("欢迎语"), "welcome_show")
        self.assertEqual(
            parse_admin_command("欢迎语 设置 欢迎入群~"), "welcome_set"
        )

    def test_batch_phrase_is_not_command(self) -> None:
        self.assertEqual(parse_admin_command("关键词 批量"), "")
        self.assertEqual(parse_admin_command("关键词 批量\n原神|好玩"), "")

    async def test_plain_text_is_not_handled(self) -> None:
        handled, reply = await handle_admin_command(
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            "原神",
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")

    async def test_welcome_set_is_handled(self) -> None:
        handled, reply = await handle_admin_command(
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            "欢迎语 设置 欢迎入群~",
        )
        self.assertTrue(handled)
        self.assertIn("欢迎入群~", reply)
        self.assertEqual(self.welcome.get_content(self.group_id), "欢迎入群~")

    async def test_welcome_stranger_is_silent(self) -> None:
        handled, reply = await handle_admin_command(
            self.welcome,
            FakeEvent(admin=False),
            self.group_id,
            "欢迎语 设置 欢迎入群~",
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")
        self.assertIsNone(self.welcome.get_content(self.group_id))

    async def test_qq_admin_can_set_welcome(self) -> None:
        handled, reply = await handle_admin_command(
            self.welcome,
            FakeEvent(admin=False, role="admin"),
            self.group_id,
            "欢迎语 设置 管理写的",
        )
        self.assertTrue(handled)
        self.assertIn("管理写的", reply)
