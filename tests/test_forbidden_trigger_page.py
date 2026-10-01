# WebUI 违禁触发词表：分页、过滤、新增、修改、删除。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_trigger_page import (
    list_triggers,
    remove_trigger,
    save_trigger,
)
from astrbot_plugin_w1ndys_rules.data.forbidden_store import ForbiddenStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_GLOBAL_SCOPE,
    FORBIDDEN_KIND_TRIGGER,
)


class ForbiddenTriggerPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_list_pages_and_filter(self) -> None:
        await self.store.add(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, "广告")
        await self.store.add(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, "加微")
        await self.store.add(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, "兼职")
        data = list_triggers(self.store, {"q": "加", "page": 1, "page_size": 10})
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["content"], "加微")

    async def test_save_add_update_delete(self) -> None:
        ok, message = await save_trigger(self.store, {"content": "广告"})
        self.assertTrue(ok)
        self.assertIn("添加", message)
        ok, message = await save_trigger(
            self.store, {"old_content": "广告", "content": "加群"}
        )
        self.assertTrue(ok)
        self.assertIn("修改", message)
        words = self.store.list_contents(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER)
        self.assertEqual(words, ["加群"])
        ok, message = await remove_trigger(self.store, {"content": "加群"})
        self.assertTrue(ok)
        self.assertEqual(
            self.store.list_contents(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER),
            [],
        )

    async def test_save_rejects_empty(self) -> None:
        ok, message = await save_trigger(self.store, {"content": "  "})
        self.assertFalse(ok)
        self.assertIn("空", message)

    async def test_add_duplicate(self) -> None:
        await save_trigger(self.store, {"content": "广告"})
        ok, message = await save_trigger(self.store, {"content": "广告"})
        self.assertFalse(ok)
        self.assertIn("已经存在", message)
