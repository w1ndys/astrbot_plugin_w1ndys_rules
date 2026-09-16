# 批量导入不依赖 AstrBot，只测格式解析、权限、冲突和落库。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.keyword_batch import (
    import_rules,
    split_keyword_reply,
    strip_command_header,
)
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    KEYWORD_BATCH_DETAIL_LIMIT,
    KEYWORD_BATCH_MAX_LINES,
)


class FakeContext:
    """测试用的唤醒前缀配置。没有 AstrBot 时用这个冒充 context。"""

    def __init__(self, prefixes: list[str] | None = None) -> None:
        # 没指定前缀就用默认 /，和 AstrBot 兜底值一致
        if prefixes is None:
            self._prefixes = ["/"]
        else:
            self._prefixes = prefixes

    def get_config(self) -> dict:
        """给 wake_prefix.prefixes 读的那一层配置。"""
        return {"wake_prefix": self._prefixes}


class FakeEvent:
    """测试用的发言人。只提供 is_admin，用来挡非管理员。"""

    def __init__(self, admin: bool = True) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        """当前发言人是不是管理员。"""
        return self._admin


class KeywordBatchTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KeywordStore(Path(self._tmp.name) / "rules.db")
        self.context = FakeContext(["卷卷", "/"])
        self.event = FakeEvent(admin=True)
        self.group_id = "123456"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strip_command_header_keeps_payload_lines(self) -> None:
        text = "关键词 批量\n原神|好玩\n你好|你好呀"
        self.assertEqual(strip_command_header(text), "原神|好玩\n你好|你好呀")

    def test_strip_command_header_same_line_payload(self) -> None:
        self.assertEqual(strip_command_header("关键词 批量 原神|好玩"), "原神|好玩")

    def test_strip_command_header_when_command_already_gone(self) -> None:
        self.assertEqual(strip_command_header("原神|好玩"), "原神|好玩")

    def test_split_supports_pipe_fullwidth_and_tab(self) -> None:
        self.assertEqual(split_keyword_reply("原神|好玩"), ("原神", "好玩"))
        self.assertEqual(split_keyword_reply("原神｜好玩"), ("原神", "好玩"))
        self.assertEqual(split_keyword_reply("原神\t好玩"), ("原神", "好玩"))
        self.assertIsNone(split_keyword_reply("原神 好玩"))

    def test_split_uses_the_earliest_separator(self) -> None:
        self.assertEqual(split_keyword_reply("a|b｜c"), ("a", "b｜c"))

    async def test_empty_payload_returns_usage(self) -> None:
        text = await import_rules(
            self.context, self.store, self.event, self.group_id, "关键词 批量"
        )
        self.assertIn("用法", text)
        self.assertIn("关键词 批量", text)
        self.assertNotIn("卷卷关键词 批量", text)

    async def test_non_admin_is_rejected(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            FakeEvent(admin=False),
            self.group_id,
            "关键词 批量\n原神|好玩",
        )
        self.assertEqual(text, "只有 AstrBot 管理员能管理本群的关键词回复。")
        self.assertEqual(self.store.find_reply(self.group_id, "原神"), "")

    async def test_adds_new_rules(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n原神|好玩\n你好|你好呀",
        )
        self.assertIn("新增 2 条", text)
        self.assertIn("冲突 0 条", text)
        self.assertEqual(self.store.find_reply(self.group_id, "原神"), "好玩")
        self.assertEqual(self.store.find_reply(self.group_id, "你好"), "你好呀")

    async def test_conflict_does_not_overwrite(self) -> None:
        await self.store.upsert(self.group_id, "原神", "好玩")
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n原神|没意思",
        )
        self.assertIn("冲突 1 条", text)
        self.assertIn("「原神」", text)
        self.assertEqual(self.store.find_reply(self.group_id, "原神"), "好玩")

    async def test_duplicate_in_batch_keeps_first(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n原神|好玩\n原神|没意思",
        )
        self.assertIn("新增 1 条", text)
        self.assertIn("跳过 1 条", text)
        self.assertIn("本批里重复", text)
        self.assertEqual(self.store.find_reply(self.group_id, "原神"), "好玩")

    async def test_wake_prefix_keyword_is_skipped(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n卷卷你好|嗨",
        )
        self.assertIn("跳过 1 条", text)
        self.assertIn("唤醒前缀", text)
        self.assertEqual(self.store.find_reply(self.group_id, "卷卷你好"), "")

    async def test_line_without_separator_is_skipped(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n原神好玩",
        )
        self.assertIn("没有用「|」分开", text)
        self.assertEqual(self.store.list_rules(self.group_id), [])

    async def test_empty_lines_are_ignored(self) -> None:
        text = await import_rules(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "关键词 批量\n原神|好玩\n\n\n你好|你好呀\n",
        )
        self.assertIn("新增 2 条", text)
        self.assertIn("跳过 0 条", text)

    async def test_too_many_lines_write_nothing(self) -> None:
        payload = "关键词 批量\n" + "\n".join(
            f"词{i}|回{i}" for i in range(KEYWORD_BATCH_MAX_LINES + 1)
        )
        text = await import_rules(
            self.context, self.store, self.event, self.group_id, payload
        )
        self.assertIn("一次最多导入", text)
        self.assertIn("这次没有写入", text)
        self.assertEqual(self.store.list_rules(self.group_id), [])

    async def test_skip_details_are_capped(self) -> None:
        payload = "关键词 批量\n" + "\n".join(
            f"坏行{i}" for i in range(KEYWORD_BATCH_DETAIL_LIMIT + 3)
        )
        text = await import_rules(
            self.context, self.store, self.event, self.group_id, payload
        )
        self.assertIn("其余 3 条未显示", text)


if __name__ == "__main__":
    unittest.main()
