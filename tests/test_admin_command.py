# 管理命令：欢迎语设/查重新认；功能开/关仍不认；批量只认 AstrBot 管理员。

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
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import CMD_KEYWORD_BATCH


class FakeContext:
    """测试用的唤醒前缀配置。自然语言校验仍要读前缀。"""

    def __init__(self, prefixes: list[str] | None = None) -> None:
        # 没指定前缀就用默认 /
        if prefixes is None:
            self._prefixes = ["/"]
        else:
            self._prefixes = prefixes

    def get_config(self) -> dict:
        """给 wake_prefix.prefixes 读的那一层配置。"""
        return {"wake_prefix": self._prefixes}


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
        self.keywords = KeywordStore(db_path)
        self.welcome = WelcomeStore(db_path)
        self.context = FakeContext(["卷卷", "/"])
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

    def test_parse_batch_header(self) -> None:
        self.assertEqual(parse_admin_command(CMD_KEYWORD_BATCH), "batch")
        self.assertEqual(parse_admin_command("关键词 批量\n原神|好玩"), "batch")
        self.assertEqual(parse_admin_command("关键词 批量 原神|好玩"), "batch")
        self.assertEqual(parse_admin_command("关键词 批量导入"), "")

    async def test_plain_text_is_not_handled(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            "原神",
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")

    async def test_welcome_set_is_handled(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
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
            self.context,
            self.keywords,
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
            self.context,
            self.keywords,
            self.welcome,
            FakeEvent(admin=False, role="admin"),
            self.group_id,
            "欢迎语 设置 管理写的",
        )
        self.assertTrue(handled)
        self.assertIn("管理写的", reply)
