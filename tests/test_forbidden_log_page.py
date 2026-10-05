# WebUI 违禁日志只读接口：列表不含原文，详情给 img src。

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_log_page import get_log, list_logs
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import FORBIDDEN_REASON_MODEL


class ForbiddenLogPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenLogStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_list_omits_originals(self) -> None:
        await self.store.insert(
            "123",
            "10001",
            FORBIDDEN_REASON_MODEL,
            "文本模型命中：广告",
            "这里有广告",
            json.dumps([{"prompt": "群名片"}], ensure_ascii=False),
            json.dumps([{"ok": True, "data": "abc"}], ensure_ascii=False),
            "小明",
        )
        data = list_logs(self.store, {"page": 1, "page_size": 20})
        self.assertEqual(data["total"], 1)
        row = data["items"][0]
        self.assertNotIn("text", row)
        self.assertNotIn("json", row)
        self.assertNotIn("images", row)
        self.assertNotIn("pictures", row)
        self.assertEqual(row["group_id"], "123")
        self.assertEqual(row["sender_name"], "小明")

    async def test_detail_pictures_use_src(self) -> None:
        log_id = await self.store.insert(
            "123",
            "10001",
            FORBIDDEN_REASON_MODEL,
            "文本模型命中：广告",
            "这里有广告",
            "[]",
            json.dumps(
                [{"ok": True, "data": "iVBOR"}, {"ok": False}],
                ensure_ascii=False,
            ),
        )
        ok, detail = get_log(self.store, {"id": log_id})
        self.assertTrue(ok)
        self.assertEqual(detail["text"], "这里有广告")
        # 详情也要带群昵称，旧日志读出来是空串
        self.assertEqual(detail["sender_name"], "")
        self.assertEqual(detail["pictures"][0]["ok"], True)
        self.assertTrue(detail["pictures"][0]["src"].startswith("data:image/png;base64,"))
        self.assertNotIn("data", detail["pictures"][0])
        self.assertEqual(detail["pictures"][1], {"ok": False})
        self.assertNotIn("images", detail)

    async def test_missing_log(self) -> None:
        ok, message = get_log(self.store, {"id": 9})
        self.assertFalse(ok)
        self.assertIn("没有", message)
