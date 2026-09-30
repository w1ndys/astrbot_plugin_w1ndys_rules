# 关键词回复：WebUI 名单外不回；名单内整句相等才回。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.keyword_reply import pick_reply
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.entity.constants import CFG_KEYWORD_GROUPS


class KeywordReplyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KeywordStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_off_does_not_reply(self) -> None:
        await self.store.upsert("123", "原神", "好玩")
        self.assertEqual(pick_reply(self.store, {}, "123", "原神"), "")

    async def test_on_replies_exact_keyword(self) -> None:
        await self.store.upsert("123", "原神", "好玩")
        config = {CFG_KEYWORD_GROUPS: ["123"]}
        self.assertEqual(pick_reply(self.store, config, "123", "原神"), "好玩")
        self.assertEqual(pick_reply(self.store, config, "123", "原神啊"), "")
