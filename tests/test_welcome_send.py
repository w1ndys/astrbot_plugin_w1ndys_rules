# 入群欢迎：开关关闭不发；没设文案用默认句。

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
from astrbot_plugin_w1ndys_rules.business.welcome_send import (
    is_group_increase,
    pick_welcome,
)
from astrbot_plugin_w1ndys_rules.data.welcome_store import WelcomeStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    DEFAULT_WELCOME_TEXT,
    FEATURE_WELCOME,
)


class FakeMessage:
    def __init__(self, raw) -> None:
        self.raw_message = raw


class FakeEvent:
    def __init__(self, raw=None, has_obj: bool = True) -> None:
        # 没有消息对象时不是入群通知
        if has_obj:
            self.message_obj = FakeMessage(raw)
        else:
            self.message_obj = None


class WelcomeSendTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "rules.db"
        self.welcome = WelcomeStore(db_path)
        self.switches = GroupSwitchStore(db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_notice_is_group_increase(self) -> None:
        event = FakeEvent({"notice_type": "group_increase", "user_id": "10001"})
        self.assertTrue(is_group_increase(event))

    def test_plain_message_is_not_increase(self) -> None:
        event = FakeEvent({"post_type": "message"})
        self.assertFalse(is_group_increase(event))
        self.assertFalse(is_group_increase(FakeEvent(has_obj=False)))

    async def test_off_sends_nothing(self) -> None:
        await self.welcome.set_content("123", "欢迎入群~")
        self.assertEqual(pick_welcome(self.welcome, self.switches, "123"), "")

    async def test_on_without_text_uses_default(self) -> None:
        await self.switches.set_on("123", FEATURE_WELCOME, True)
        self.assertEqual(
            pick_welcome(self.welcome, self.switches, "123"),
            DEFAULT_WELCOME_TEXT,
        )

    async def test_on_uses_saved_text(self) -> None:
        await self.switches.set_on("123", FEATURE_WELCOME, True)
        await self.welcome.set_content("123", "请先看群规")
        self.assertEqual(
            pick_welcome(self.welcome, self.switches, "123"),
            "请先看群规",
        )
