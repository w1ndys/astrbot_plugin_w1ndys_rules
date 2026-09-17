# 数据层：分群黑名单和全局黑名单。不踢人，不碰 AstrBot。
#
# 全局名单的 group_id 固定为 BLACKLIST_GLOBAL_SCOPE，和旧 BlackList 一致。
# 入群/发言还不走这里，所以不常驻快照，读的时候查库。

import asyncio
from datetime import datetime
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.constants import BLACKLIST_GLOBAL_SCOPE

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS blacklist (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
)
"""


class BlacklistStore:
    """黑名单表。同一群同一人只有一行；全局和群名单分开存。"""

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

    def is_in(self, group_id: str, user_id: str) -> bool:
        """这个人是否在指定名单里。只查这一张名单，不含另一张。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM blacklist WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        # 没有这一行就当不在名单里
        if row is None:
            return False
        return True

    def is_blocked(self, group_id: str, user_id: str) -> bool:
        """这个人在本群名单或全局名单里就算拉黑。"""
        # 全局优先语义：任一命中即拉黑
        if self.is_in(BLACKLIST_GLOBAL_SCOPE, user_id):
            return True
        return self.is_in(group_id, user_id)

    def list_user_ids(self, group_id: str) -> list[str]:
        """列出一张名单里的 QQ 号，按加入时间再按 QQ 号。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT user_id FROM blacklist WHERE group_id = ? "
                "ORDER BY created_at, user_id",
                (group_id,),
            ).fetchall()
        finally:
            conn.close()
        return [str(row[0]) for row in rows]

    async def add(self, group_id: str, user_id: str) -> bool:
        """写入名单。已存在返回 False，不覆盖时间。"""
        async with self._lock:
            return await asyncio.to_thread(self._add_sync, group_id, user_id)

    def _add_sync(self, group_id: str, user_id: str) -> bool:
        """同步插入。主键冲突表示已经在名单里。"""
        # 已经在了就不要再写，避免把加入时间改掉
        if self.is_in(group_id, user_id):
            return False
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO blacklist(group_id, user_id, created_at) VALUES (?, ?, ?)",
                (group_id, user_id, created_at),
            )
            conn.commit()
        finally:
            conn.close()
        return True

    async def remove(self, group_id: str, user_id: str) -> bool:
        """从指定名单删掉。本来就不在返回 False。"""
        async with self._lock:
            return await asyncio.to_thread(self._remove_sync, group_id, user_id)

    def _remove_sync(self, group_id: str, user_id: str) -> bool:
        """同步删除。"""
        conn = connect(self.db_path)
        try:
            cur = conn.execute(
                "DELETE FROM blacklist WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            conn.commit()
            # 一行都没删到，说明本来就不在这张名单
            if cur.rowcount <= 0:
                return False
            return True
        finally:
            conn.close()
