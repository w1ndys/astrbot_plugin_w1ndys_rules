# 数据层：每个群每个成员一条邀请边，记录是谁把他拉进群的。
#
# 退群不删，邀请树保留历史；重复入群按 (群号, QQ) 覆盖成最新的邀请人。
# 入群通知不常发，不必常驻快照，读的时候查库。写加锁，避免两个人同时入群互相覆盖。

import asyncio
from datetime import datetime
from pathlib import Path

from ..entity.invite import InviteEdge
from .db import connect, create_table

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

    def list_direct_downline(self, group_id: str, inviter_id: str) -> list[str]:
        """列出这个人在本群直接邀请过的 QQ 号，按号码排序。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT user_id FROM invite_edge "
                "WHERE group_id = ? AND inviter_id = ? "
                "ORDER BY user_id",
                (group_id, inviter_id),
            ).fetchall()
        finally:
            conn.close()
        return [str(row[0]) for row in rows]

    def list_edges(self, group_id: str) -> list[InviteEdge]:
        """取本群全部邀请边。WebUI 建整棵树时一次读进内存。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, user_id, inviter_id, sub_type, created_at "
                "FROM invite_edge WHERE group_id = ? ORDER BY user_id",
                (group_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_edge_from_row(row) for row in rows]

    def list_groups_of_user(self, user_id: str) -> list[str]:
        """列出这个 QQ 作为成员或邀请人出现过的群，按群号排序。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT group_id FROM invite_edge "
                "WHERE user_id = ? OR inviter_id = ? ORDER BY group_id",
                (user_id, user_id),
            ).fetchall()
        finally:
            conn.close()
        return [str(row[0]) for row in rows]

    def list_page(
        self, group_id: str, user_id: str, offset: int, limit: int
    ) -> tuple[list[InviteEdge], int]:
        """全部邀请记录分页。群号和 QQ 都为空就不加过滤。"""
        where, params = _filter_clause(group_id, user_id)
        conn = connect(self.db_path)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM invite_edge" + where, params
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT group_id, user_id, inviter_id, sub_type, created_at "
                "FROM invite_edge" + where + " ORDER BY created_at DESC, user_id "
                "LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        finally:
            conn.close()
        return [_edge_from_row(row) for row in rows], int(total)

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


def _edge_from_row(row: tuple) -> InviteEdge:
    """把 SELECT 的一行还原成邀请边。列顺序和上面的 SELECT 一致。"""
    return InviteEdge(str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))


def _filter_clause(group_id: str, user_id: str) -> tuple[str, list]:
    """拼出可选的过滤条件。值全部走 SQL 参数，不拼进语句。"""
    clauses = []
    params = []
    # 群号为空表示看全部群
    if group_id:
        clauses.append("group_id = ?")
        params.append(group_id)
    # QQ 号在邀请人和被邀请人两侧都算匹配
    if user_id:
        clauses.append("(user_id = ? OR inviter_id = ?)")
        params.extend([user_id, user_id])
    # 没有过滤条件时语句不带 WHERE
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params
