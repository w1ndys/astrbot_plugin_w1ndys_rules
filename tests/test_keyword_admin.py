# 单条关键词管理：删除不校验唤醒前缀，写入仍校验；添加和修改合成一次写入。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.keyword_admin import (
    REJECT_MESSAGE,
    delete_rule,
    write_rule,
)
from astrbot_plugin_w1ndys_rules.data.keyword_store import KeywordStore
from astrbot_plugin_w1ndys_rules.entity.constants import KEYWORD_MAX_LEN


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


class KeywordAdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KeywordStore(Path(self._tmp.name) / "rules.db")
        self.context = FakeContext(["卷卷", "/"])
        self.event = FakeEvent(admin=True)
        self.group_id = "123456"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_delete_ignores_wake_prefix(self) -> None:
        """库里已有带前缀的词时，删除不能被前缀校验拦住。"""
        await self.store.upsert(self.group_id, "/带前缀", "旧回复")
        message = await delete_rule(
            self.store, self.event, self.group_id, "/带前缀"
        )
        self.assertEqual(message, "已删除关键词「/带前缀」。")
        self.assertIsNone(self.store.rule_of(self.group_id, "/带前缀"))

    async def test_delete_strips_and_rejects_empty(self) -> None:
        """删除仍去掉首尾空白；空词对不上规则，直接拒绝。"""
        empty = await delete_rule(self.store, self.event, self.group_id, "   ")
        self.assertEqual(empty, "关键词不能是空的。")

    async def test_delete_still_rejects_too_long(self) -> None:
        """删除仍拦超长词，只是不再拦唤醒前缀。"""
        too_long = "a" * (KEYWORD_MAX_LEN + 1)
        message = await delete_rule(
            self.store, self.event, self.group_id, too_long
        )
        self.assertEqual(
            message, f"关键词太长了，最多 {KEYWORD_MAX_LEN} 个字。"
        )

    async def test_delete_missing_keyword(self) -> None:
        """本群没有这条时不能回报成删除成功。"""
        message = await delete_rule(
            self.store, self.event, self.group_id, "/也不存在"
        )
        self.assertEqual(message, "本群没有关键词「/也不存在」，没有删除。")

    async def test_delete_rejects_non_admin(self) -> None:
        """非管理员不能删，库里的词要还在。"""
        await self.store.upsert(self.group_id, "/带前缀", "旧回复")
        message = await delete_rule(
            self.store, FakeEvent(admin=False), self.group_id, "/带前缀"
        )
        self.assertEqual(message, REJECT_MESSAGE)
        self.assertIsNotNone(self.store.rule_of(self.group_id, "/带前缀"))

    async def test_write_still_rejects_wake_prefix(self) -> None:
        """写入路径仍拦唤醒前缀，避免永远匹配不到的规则进库。"""
        message = await write_rule(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "/新词",
            "新回复",
        )
        self.assertIn("不能以「/」开头", message)
        self.assertIsNone(self.store.rule_of(self.group_id, "/新词"))

    async def test_write_adds_missing_keyword(self) -> None:
        """本群没有这条时直接新增，不要求模型先判断存在性。"""
        message = await write_rule(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "不存在的词",
            "abc",
        )
        self.assertEqual(
            message, "已添加关键词「不存在的词」，命中后回复「abc」。"
        )
        rule = self.store.rule_of(self.group_id, "不存在的词")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.reply, "abc")

    async def test_write_covers_existing_keyword(self) -> None:
        """已有关键词时覆盖回复，并如实回报覆盖。"""
        await self.store.upsert(self.group_id, "晚安", "旧回复")
        message = await write_rule(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "晚安",
            "早点睡",
        )
        self.assertEqual(
            message, "已覆盖关键词「晚安」，命中后回复「早点睡」。"
        )
        rule = self.store.rule_of(self.group_id, "晚安")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.reply, "早点睡")

    async def test_write_skips_same_reply(self) -> None:
        """回复没变就不写库，避免无意义覆盖。"""
        await self.store.upsert(self.group_id, "晚安", "早点睡")
        message = await write_rule(
            self.context,
            self.store,
            self.event,
            self.group_id,
            "晚安",
            "早点睡",
        )
        self.assertEqual(
            message, "关键词「晚安」的回复本来就是「早点睡」，没有改动。"
        )

    async def test_write_rejects_non_admin(self) -> None:
        """非管理员不能写，库里不能出现这条。"""
        message = await write_rule(
            self.context,
            self.store,
            FakeEvent(admin=False),
            self.group_id,
            "不存在的词",
            "abc",
        )
        self.assertEqual(message, REJECT_MESSAGE)
        self.assertIsNone(self.store.rule_of(self.group_id, "不存在的词"))
