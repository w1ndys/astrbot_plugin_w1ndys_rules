# 数据层：违禁触发词的 SQLite 存取。表仍按 group_id+kind 存，业务层用全局作用域。

import asyncio
import sqlite3
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.forbidden import ForbiddenItem

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS forbidden_item (
    group_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (group_id, kind, content)
)
"""


class ForbiddenStore:
    """按作用域和类型保存配置，内存快照供群消息热路径读取。"""

    def __init__(self, db_path: Path) -> None:
        """建表并加载内存快照。"""
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._snapshot: dict[tuple[str, str], list[ForbiddenItem]] = {}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()
        self._load_snapshot()

    def _setup(self) -> None:
        """首次启动时创建违禁配置表。"""
        conn = connect(self.db_path)
        try:
            create_table(conn, CREATE_TABLE_SQL)
        finally:
            conn.close()

    def _load_snapshot(self) -> None:
        """从 SQLite 重建按群、按类型分组的内存快照。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, kind, content FROM forbidden_item ORDER BY content"
            ).fetchall()
        finally:
            conn.close()
        snapshot: dict[tuple[str, str], list[ForbiddenItem]] = {}
        for row in rows:
            item = ForbiddenItem(str(row[0]), str(row[1]), str(row[2]))
            key = (item.group_id, item.kind)
            # 首条数据先创建当前群和类型的列表。
            if key not in snapshot:
                snapshot[key] = []
            snapshot[key].append(item)
        self._snapshot = snapshot

    def list_contents(self, group_id: str, kind: str) -> list[str]:
        """返回本群指定类型的全部内容，按内容排序。"""
        items = self._snapshot.get((group_id, kind), [])
        return [item.content for item in items]

    def contains(self, group_id: str, kind: str, content: str) -> bool:
        """判断本群指定类型是否已有完全相同的内容。"""
        return content in self.list_contents(group_id, kind)

    async def add(self, group_id: str, kind: str, content: str) -> bool:
        """新增一条内容；重复时返回 False，不覆盖。"""
        async with self._lock:
            added = await asyncio.to_thread(self._add_sync, group_id, kind, content)
            # 只有数据库发生变化才重建快照。
            if added:
                await asyncio.to_thread(self._load_snapshot)
        return added

    async def update(
        self,
        group_id: str,
        kind: str,
        old_content: str,
        new_content: str,
    ) -> str:
        """修改一条内容，返回 missing、conflict 或 updated。"""
        async with self._lock:
            result = await asyncio.to_thread(
                self._update_sync,
                group_id,
                kind,
                old_content,
                new_content,
            )
            # 修改成功后立即刷新热路径快照。
            if result == "updated":
                await asyncio.to_thread(self._load_snapshot)
        return result

    async def delete(self, group_id: str, kind: str, content: str) -> bool:
        """删除一条内容，返回数据库是否真的删掉一行。"""
        async with self._lock:
            removed = await asyncio.to_thread(
                self._delete_sync, group_id, kind, content
            )
            # 删除成功后立即刷新热路径快照。
            if removed:
                await asyncio.to_thread(self._load_snapshot)
        return removed

    def _add_sync(self, group_id: str, kind: str, content: str) -> bool:
        """在线程中新增一行，唯一键冲突表示内容已存在。"""
        conn = connect(self.db_path)
        try:
            try:
                conn.execute(
                    "INSERT INTO forbidden_item(group_id, kind, content) "
                    "VALUES (?, ?, ?)",
                    (group_id, kind, content),
                )
            except sqlite3.IntegrityError:
                return False
            conn.commit()
            return True
        finally:
            conn.close()

    def _update_sync(
        self,
        group_id: str,
        kind: str,
        old_content: str,
        new_content: str,
    ) -> str:
        """在线程中原子修改一行，并区分不存在和新内容冲突。"""
        conn = connect(self.db_path)
        try:
            # 先锁住写事务，再检查和修改，避免并发写者插入或删除旧内容。
            conn.execute("BEGIN IMMEDIATE")
            old_exists = self._row_exists(conn, group_id, kind, old_content)
            # 原内容不存在时不能悄悄新增。
            if not old_exists:
                return "missing"
            new_exists = self._row_exists(conn, group_id, kind, new_content)
            # 新内容已存在时保留两条原数据，不覆盖。
            if new_exists:
                return "conflict"
            conn.execute(
                "UPDATE forbidden_item SET content = ? "
                "WHERE group_id = ? AND kind = ? AND content = ?",
                (new_content, group_id, kind, old_content),
            )
            conn.commit()
            return "updated"
        finally:
            conn.close()

    def _delete_sync(self, group_id: str, kind: str, content: str) -> bool:
        """在线程中删除一行并返回是否命中。"""
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM forbidden_item "
                "WHERE group_id = ? AND kind = ? AND content = ?",
                (group_id, kind, content),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def _row_exists(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        kind: str,
        content: str,
    ) -> bool:
        """在当前事务里判断唯一键对应的行是否存在。"""
        row = conn.execute(
            "SELECT 1 FROM forbidden_item "
            "WHERE group_id = ? AND kind = ? AND content = ?",
            (group_id, kind, content),
        ).fetchone()
        return row is not None
