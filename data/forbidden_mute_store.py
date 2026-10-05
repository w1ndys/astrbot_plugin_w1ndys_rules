# 数据层：记下「这次禁言是违禁造成的」。
#
# 只记群号和成员。管理员解开这次禁言时才会加本群白名单，机器人自己和到期解禁都不算。
# 没有标记的普通解禁不能当成加白依据，所以必须单独存一张表。

import asyncio
from datetime import datetime
from pathlib import Path

from .db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS forbidden_mute (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
)
"""


class ForbiddenMuteStore:
    """违禁禁言标记表。同一群同一人一行，重复标记覆盖时间。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _setup(self) -> None:
        """首次启动时建表。已存在就跳过。"""
        conn = connect(self.db_path)
        try:
            create_table(conn, CREATE_TABLE_SQL)
        finally:
            conn.close()

    async def mark(self, group_id: str, user_id: str) -> None:
        """记下这一对。已经记过就覆盖时间。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_sync, group_id, user_id)

    def _mark_sync(self, group_id: str, user_id: str) -> None:
        """同步写入。主键冲突时只改时间，不插第二行。"""
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO forbidden_mute(group_id, user_id, created_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(group_id, user_id) "
                "DO UPDATE SET created_at = excluded.created_at",
                (group_id, user_id, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def has(self, group_id: str, user_id: str) -> bool:
        """这一对有没有违禁禁言标记。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM forbidden_mute WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        # 没有这一行说明不是违禁禁言
        if row is None:
            return False
        return True

    async def clear(self, group_id: str, user_id: str) -> bool:
        """删掉这一对的标记。本来就没有返回 False。"""
        async with self._lock:
            return await asyncio.to_thread(self._clear_sync, group_id, user_id)

    def _clear_sync(self, group_id: str, user_id: str) -> bool:
        """同步删除。"""
        conn = connect(self.db_path)
        try:
            cur = conn.execute(
                "DELETE FROM forbidden_mute WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            conn.commit()
            # 一行都没删到，说明本来就没有标记
            if cur.rowcount <= 0:
                return False
            return True
        finally:
            conn.close()
