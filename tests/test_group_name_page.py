# 群名 Pages 业务：列出映射、拆 get_group_list、保存草稿且不删旧行。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.group_name_page import (
    list_group_names,
    parse_group_list,
    pull_group_names,
    save_group_names,
)
from astrbot_plugin_w1ndys_rules.data.group_name_store import GroupNameStore


class GroupNamePageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = GroupNameStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_empty(self) -> None:
        data = list_group_names(self.store)
        self.assertEqual(data, {"items": []})

    async def test_list_after_save(self) -> None:
        ok, message = await save_group_names(
            self.store,
            {"items": [{"group_id": "1127665319", "group_name": "推荐群聊"}]},
        )
        self.assertTrue(ok)
        self.assertIn("保存", message)
        data = list_group_names(self.store)
        self.assertEqual(
            data["items"],
            [{"group_id": "1127665319", "group_name": "推荐群聊"}],
        )

    def test_parse_direct_list(self) -> None:
        items = parse_group_list(
            [{"group_id": 1127665319, "group_name": "推荐群聊"}]
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].group_id, "1127665319")
        self.assertEqual(items[0].group_name, "推荐群聊")

    def test_parse_wrapped_data(self) -> None:
        items = parse_group_list(
            {"data": [{"group_id": "1", "group_name": "甲"}]}
        )
        self.assertEqual(items[0].group_id, "1")
        self.assertEqual(items[0].group_name, "甲")

    def test_parse_skips_empty_group_id(self) -> None:
        items = parse_group_list(
            [{"group_id": "", "group_name": "丢"}, {"group_name": "也丢"}]
        )
        self.assertEqual(items, [])

    def test_parse_unknown_shape_is_empty(self) -> None:
        self.assertEqual(parse_group_list(None), [])
        self.assertEqual(parse_group_list({"data": {}}), [])

    def test_pull_matches_list_shape(self) -> None:
        data = pull_group_names(
            {"data": [{"group_id": "1", "group_name": "甲"}]}
        )
        self.assertEqual(data, {"items": [{"group_id": "1", "group_name": "甲"}]})

    async def test_save_rejects_bad_items(self) -> None:
        ok, message = await save_group_names(self.store, {"items": "1"})
        self.assertFalse(ok)
        self.assertIn("列表", message)
        self.assertEqual(self.store.as_map(), {})

    async def test_save_keeps_old_rows(self) -> None:
        await save_group_names(
            self.store,
            {"items": [{"group_id": "1", "group_name": "甲"}]},
        )
        await save_group_names(
            self.store,
            {"items": [{"group_id": "2", "group_name": "乙"}]},
        )
        mapping = self.store.as_map()
        self.assertEqual(mapping["1"], "甲")
        self.assertEqual(mapping["2"], "乙")
