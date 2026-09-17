# 管理命令不依赖 AstrBot 指令过滤器，只测识别、权限静默和开关文案。

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
from astrbot_plugin_w1ndys_rules.business.admin_command import (
    handle_admin_command,
    parse_admin_command,
)
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CMD_FORBIDDEN_OFF,
    CMD_FORBIDDEN_ON,
    CMD_KEYWORD_BATCH,
    CMD_KEYWORD_OFF,
    CMD_KEYWORD_ON,
    CMD_WELCOME_OFF,
    CMD_WELCOME_ON,
    CMD_WELCOME_SET,
    CMD_WELCOME_SHOW,
    FEATURE_FORBIDDEN,
    FEATURE_KEYWORD,
    FEATURE_WELCOME,
)


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


class FakeEvent:
    """测试用的发言人。只提供 is_admin。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        """当前发言人是不是管理员。"""
        return self._admin


class AdminCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.keywords = KeywordStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        self.welcome = WelcomeStore(db_path)
        self.context = FakeContext(["卷卷", "/"])
        self.group_id = "123456"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_on_off_must_be_exact(self) -> None:
        self.assertEqual(parse_admin_command(CMD_KEYWORD_ON), "keyword_on")
        self.assertEqual(parse_admin_command(CMD_KEYWORD_OFF), "keyword_off")
        self.assertEqual(parse_admin_command("关键词 开 吧"), "")
        self.assertEqual(parse_admin_command("关键词"), "")

    def test_parse_forbidden_on_off_must_be_exact(self) -> None:
        self.assertEqual(parse_admin_command(CMD_FORBIDDEN_ON), "forbidden_on")
        self.assertEqual(parse_admin_command(CMD_FORBIDDEN_OFF), "forbidden_off")
        self.assertEqual(parse_admin_command("违禁词 开 吧"), "")
        self.assertEqual(parse_admin_command("违禁词"), "")

    def test_parse_batch_header(self) -> None:
        self.assertEqual(parse_admin_command(CMD_KEYWORD_BATCH), "batch")
        self.assertEqual(parse_admin_command("关键词 批量\n原神|好玩"), "batch")
        self.assertEqual(parse_admin_command("关键词 批量 原神|好玩"), "batch")
        self.assertEqual(parse_admin_command("关键词 批量导入"), "")

    async def test_admin_on_does_not_use_wake_prefix(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            CMD_KEYWORD_ON,
        )
        self.assertTrue(handled)
        self.assertIn("已开启", reply)
        self.assertIn(CMD_KEYWORD_OFF, reply)
        self.assertNotIn("卷卷", reply)
        self.assertTrue(self.switches.is_on(self.group_id, FEATURE_KEYWORD))

    async def test_forbidden_on_does_not_enable_keyword(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            CMD_FORBIDDEN_ON,
        )
        self.assertTrue(handled)
        self.assertIn("已开启本群的违禁词", reply)
        self.assertIn(CMD_FORBIDDEN_OFF, reply)
        self.assertTrue(self.switches.is_on(self.group_id, FEATURE_FORBIDDEN))
        self.assertFalse(self.switches.is_on(self.group_id, FEATURE_KEYWORD))

    async def test_non_admin_is_silent(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=False),
            self.group_id,
            CMD_KEYWORD_ON,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")

    async def test_forbidden_non_admin_is_silent(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=False),
            self.group_id,
            CMD_FORBIDDEN_ON,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")
        self.assertFalse(self.switches.is_on(self.group_id, FEATURE_FORBIDDEN))

    async def test_plain_text_is_not_handled(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            "原神",
        )
        self.assertFalse(handled)
        self.assertEqual(reply, "")

    def test_parse_welcome_on_off_and_show_must_be_exact(self) -> None:
        self.assertEqual(parse_admin_command(CMD_WELCOME_ON), "welcome_on")
        self.assertEqual(parse_admin_command(CMD_WELCOME_OFF), "welcome_off")
        self.assertEqual(parse_admin_command(CMD_WELCOME_SHOW), "welcome_show")
        self.assertEqual(parse_admin_command("欢迎语 开 吧"), "")
        self.assertEqual(parse_admin_command("欢迎语设置"), "")

    def test_parse_welcome_set_header(self) -> None:
        self.assertEqual(parse_admin_command(CMD_WELCOME_SET), "welcome_set")
        self.assertEqual(parse_admin_command("欢迎语 设置 欢迎入群~"), "welcome_set")
        self.assertEqual(parse_admin_command("欢迎语 设置\n欢迎入群~"), "welcome_set")
        self.assertEqual(parse_admin_command("欢迎语 设置导入"), "")

    async def test_welcome_on_does_not_enable_keyword(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            CMD_WELCOME_ON,
        )
        self.assertTrue(handled)
        self.assertIn("已开启本群的欢迎语", reply)
        self.assertIn(CMD_WELCOME_OFF, reply)
        self.assertTrue(self.switches.is_on(self.group_id, FEATURE_WELCOME))
        self.assertFalse(self.switches.is_on(self.group_id, FEATURE_KEYWORD))

    async def test_welcome_set_and_show(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            "欢迎语 设置 欢迎入群~",
        )
        self.assertTrue(handled)
        self.assertIn("已设置本群欢迎语", reply)
        self.assertIn("欢迎入群~", reply)
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=True),
            self.group_id,
            CMD_WELCOME_SHOW,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "本群欢迎语：\n欢迎入群~")

    async def test_welcome_non_admin_is_silent(self) -> None:
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            self.welcome,
            FakeEvent(admin=False),
            self.group_id,
            CMD_WELCOME_ON,
        )
        self.assertTrue(handled)
        self.assertEqual(reply, "")
        self.assertFalse(self.switches.is_on(self.group_id, FEATURE_WELCOME))
