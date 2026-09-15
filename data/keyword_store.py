# 数据层：关键词回复规则的 SQLite 存取。不判断权限，不碰 AstrBot。
#
# 命中判断在热路径上（每条群消息都要过一遍），所以启动时把整张表读进内存，
# SQLite 只作为持久化。写的时候先落库、再整表重建快照，所以群消息读内存时
# 要么看到旧快照、要么看到写完之后的新快照，不会看到写了一半的状态。

import asyncio
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.keyword import KeywordRule

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS keyword_reply (
    group_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    reply TEXT NOT NULL,
    PRIMARY KEY (group_id, keyword)
)
"""


class KeywordStore:
    """关键词规则表。SQLite 负责长期保存，内存快照负责每条群消息的命中判断。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        # 内存快照：键是 (群号, 关键词)，值是整条规则。没在里面的就是没有这条关键词。
        self._snapshot: dict[tuple[str, str], KeywordRule] = {}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()
        self._load_snapshot()

    def _setup(self) -> None:
        """首次启动时建表。已存在就跳过。"""
        conn = connect(self.db_path)
        try:
            create_table(conn, CREATE_TABLE_SQL)
        finally:
            conn.close()

    def _load_snapshot(self) -> None:
        """把整张表读进内存。群号不同、关键词相同的规则各存各的。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, keyword, reply FROM keyword_reply"
            ).fetchall()
        finally:
            conn.close()
        snapshot: dict[tuple[str, str], KeywordRule] = {}
        for row in rows:
            rule = KeywordRule(str(row[0]), str(row[1]), str(row[2]))
            snapshot[(rule.group_id, rule.keyword)] = rule
        self._snapshot = snapshot

    def find_reply(self, group_id: str, text: str) -> str:
        """按群号和整条消息文本查回复。完全匹配，查不到返回空串。"""
        rule = self._snapshot.get((group_id, text))
        # 没有这条关键词就没什么可回的
        if rule is None:
            return ""
        return rule.reply

    def rule_of(self, group_id: str, keyword: str) -> KeywordRule | None:
        """取整条规则，查不到返回 None。管理员路径用它判断关键词在不在、原来回的什么。"""
        return self._snapshot.get((group_id, keyword))

    def list_rules(self, group_id: str) -> list[KeywordRule]:
        """本群全部规则，按关键词排序。只读内存快照，不查库。"""
        rules = [
            rule
            for (rule_group_id, _), rule in self._snapshot.items()
            if rule_group_id == group_id
        ]
        return sorted(rules, key=lambda rule: rule.keyword)

    async def upsert(self, group_id: str, keyword: str, reply: str) -> None:
        """新增或覆盖一条规则。写完立刻重建快照，下一条群消息就能命中。"""
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, group_id, keyword, reply)
            await asyncio.to_thread(self._load_snapshot)

    async def delete(self, group_id: str, keyword: str) -> bool:
        """删掉一条规则。返回是否真删掉了一行，用来区分「删成功」和「本来就没有」。"""
        async with self._lock:
            removed = await asyncio.to_thread(self._delete_sync, group_id, keyword)
            await asyncio.to_thread(self._load_snapshot)
        return removed

    def _upsert_sync(self, group_id: str, keyword: str, reply: str) -> None:
        """同步写库，给 to_thread 用。同群同关键词只有一行，写了就覆盖回复。"""
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO keyword_reply(group_id, keyword, reply) VALUES (?, ?, ?) "
                "ON CONFLICT(group_id, keyword) DO UPDATE SET reply = excluded.reply",
                (group_id, keyword, reply),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete_sync(self, group_id: str, keyword: str) -> bool:
        """同步删库，给 to_thread 用。返回是否真删掉了一行。"""
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM keyword_reply WHERE group_id = ? AND keyword = ?",
                (group_id, keyword),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
