# 数据层：每个群每个成员一条邀请边，记录是谁把他拉进群的。
#
# 退群不删，邀请树保留历史；重复入群按 (群号, QQ) 覆盖成最新的邀请人。
# 入群通知不常发，不必常驻快照，读的时候查库。写加锁，避免两个人同时入群互相覆盖。

import asyncio
from datetime import datetime
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.invite import InviteEdge

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS invite_edge (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    inviter_id TEXT NOT NULL,
    sub_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
)
"""


class InviteStore:
    """邀请边表。主键是群号加成员，值为把他拉进来的人和入群方式。"""

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

    def get_edge(self, group_id: str, user_id: str) -> InviteEdge | None:
        """取这个人在本群的邀请边。没有记录返回 None。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT inviter_id, sub_type FROM invite_edge "
                "WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        # 没有这一行说明入群时没开关，或拿不到邀请人没记
        if row is None:
            return None
        return InviteEdge(group_id, user_id, str(row[0]), str(row[1]))

    async def record(
        self, group_id: str, user_id: str, inviter_id: str, sub_type: str
    ) -> None:
        """写入或覆盖这个人在本群的邀请边。再次入群换最新邀请人。"""
        async with self._lock:
            await asyncio.to_thread(
                self._record_sync, group_id, user_id, inviter_id, sub_type
            )

    def _record_sync(
        self, group_id: str, user_id: str, inviter_id: str, sub_type: str
    ) -> None:
        """同步写库，给 to_thread 用。同一群同一人只保留一行。"""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO invite_edge"
                "(group_id, user_id, inviter_id, sub_type, created_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(group_id, user_id) DO UPDATE SET "
                "inviter_id = excluded.inviter_id, "
                "sub_type = excluded.sub_type, "
                "created_at = excluded.created_at",
                (group_id, user_id, inviter_id, sub_type, stamp),
            )
            conn.commit()
        finally:
            conn.close()
