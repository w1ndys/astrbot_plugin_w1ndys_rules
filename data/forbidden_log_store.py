# 数据层：违禁命中日志的 SQLite 存取。不判断权限，不碰 AstrBot。
#
# 日志会一直增长，不能像关键词那样整表进内存。读写都走 SQLite。
# 原文三列（text / json / images）更新接口默认不能改，避免详情被改掉。
# 群昵称（sender_name）是命中那一刻的快照，只在这张表里读写；回补只填空值。

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..entity.forbidden_log import ForbiddenLog
from .db import connect, create_table

_BEIJING = ZoneInfo("Asia/Shanghai")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS forbidden_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    json TEXT NOT NULL,
    images TEXT NOT NULL,
    sender_name TEXT NOT NULL DEFAULT ''
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_forbidden_log_filter
ON forbidden_log(group_id, user_id, reason_code, id)
"""


class ForbiddenLogStore:
    """违禁日志表。热路径只插入；列表和详情给以后的只读页。"""

    def __init__(self, db_path: Path) -> None:
        """建表。没有快照，读的时候查库。"""
        self.db_path = db_path
        self._lock = asyncio.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _setup(self) -> None:
        """首次启动时建表和筛选索引。旧库补群昵称列。已存在就跳过。"""
        conn = connect(self.db_path)
        try:
            create_table(conn, CREATE_TABLE_SQL)
            self._ensure_sender_name_column(conn)
            conn.execute(CREATE_INDEX_SQL)
            conn.commit()
        finally:
            conn.close()

    def _table_columns(self, conn: object) -> list[str]:
        """当前日志表有哪些列。给旧库补列用。"""
        rows = conn.execute("PRAGMA table_info(forbidden_log)").fetchall()
        return [str(row[1]) for row in rows]

    def _ensure_sender_name_column(self, conn: object) -> None:
        """旧表没有群昵称列时补上，默认空串，避免读这一列失败。"""
        names = self._table_columns(conn)
        # 新库建表时已经有这一列，不用再改
        if "sender_name" in names:
            return
        conn.execute(
            "ALTER TABLE forbidden_log "
            "ADD COLUMN sender_name TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()

    async def insert(
        self,
        group_id: str,
        user_id: str,
        reason_code: str,
        reason_text: str,
        text: str,
        json_text: str,
        images: str,
        sender_name: str = "",
    ) -> int:
        """写入一条命中日志，返回自增 id。sender_name 是命中当时的群昵称，回补只填空值。"""
        async with self._lock:
            return await asyncio.to_thread(
                self._insert_sync,
                group_id,
                user_id,
                reason_code,
                reason_text,
                text,
                json_text,
                images,
                sender_name,
            )

    def get(self, log_id: int) -> ForbiddenLog | None:
        """按 id 取一条，含原文三列。没有这条返回 None。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, group_id, user_id, reason_code, reason_text, "
                "created_at, text, json, images, sender_name FROM forbidden_log "
                "WHERE id = ?",
                (log_id,),
            ).fetchone()
        finally:
            conn.close()
        # 这个 id 还没写过，详情页要报不存在
        if row is None:
            return None
        return _row_to_log(row)

    def list_page(
        self,
        group_id: str,
        user_id: str,
        reason_code: str,
        offset: int,
        limit: int,
    ) -> tuple[list[ForbiddenLog], int]:
        """按群、用户、原因过滤后分页。空串表示这项不筛。新的在前。"""
        where_sql, args = _filter_sql(group_id, user_id, reason_code)
        # 负偏移当成从开头切
        offset = max(offset, 0)
        # 每页条数非法时不要查行，仍要报总数
        if limit <= 0:
            return [], self._count(where_sql, args)
        conn = connect(self.db_path)
        try:
            total_row = conn.execute(
                "SELECT COUNT(*) FROM forbidden_log" + where_sql, args
            ).fetchone()
            rows = conn.execute(
                "SELECT id, group_id, user_id, reason_code, reason_text, "
                "created_at, text, json, images, sender_name FROM forbidden_log"
                + where_sql
                + " ORDER BY id DESC LIMIT ? OFFSET ?",
                args + [limit, offset],
            ).fetchall()
        finally:
            conn.close()
        total = int(total_row[0]) if total_row else 0
        items = []
        for row in rows:
            items.append(_row_to_log(row))
        return items, total

    async def update_reason(
        self, log_id: int, reason_code: str, reason_text: str
    ) -> bool:
        """只改原因码和人话。原文三列不动。没有这条返回 False。"""
        async with self._lock:
            return await asyncio.to_thread(
                self._update_reason_sync, log_id, reason_code, reason_text
            )

    async def delete(self, log_id: int) -> bool:
        """按 id 删一条。没有这条返回 False。HTTP 这一版不挂。"""
        async with self._lock:
            return await asyncio.to_thread(self._delete_sync, log_id)

    def _count(self, where_sql: str, args: list) -> int:
        """按同一套筛选条件数总数。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM forbidden_log" + where_sql, args
            ).fetchone()
        finally:
            conn.close()
        # 空表或条件没命中都是 0
        if row is None:
            return 0
        return int(row[0])

    def _insert_sync(
        self,
        group_id: str,
        user_id: str,
        reason_code: str,
        reason_text: str,
        text: str,
        json_text: str,
        images: str,
        sender_name: str = "",
    ) -> int:
        """同步插入，给 to_thread 用。时间用北京时间。"""
        stamp = datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO forbidden_log("
                "group_id, user_id, reason_code, reason_text, created_at, "
                "text, json, images, sender_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    group_id,
                    user_id,
                    reason_code,
                    reason_text,
                    stamp,
                    text,
                    json_text,
                    images,
                    sender_name,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _update_reason_sync(
        self, log_id: int, reason_code: str, reason_text: str
    ) -> bool:
        """同步只改原因，给 to_thread 用。"""
        conn = connect(self.db_path)
        try:
            cur = conn.execute(
                "UPDATE forbidden_log SET reason_code = ?, reason_text = ? "
                "WHERE id = ?",
                (reason_code, reason_text, log_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def _delete_sync(self, log_id: int) -> bool:
        """同步删除，给 to_thread 用。"""
        conn = connect(self.db_path)
        try:
            cur = conn.execute("DELETE FROM forbidden_log WHERE id = ?", (log_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def _filter_sql(group_id: str, user_id: str, reason_code: str) -> tuple[str, list]:
    """拼 WHERE。空串不作为筛选条件。"""
    clauses = []
    args: list = []
    group = group_id.strip()
    # 填了群号就只看这一群
    if group:
        clauses.append("group_id = ?")
        args.append(group)
    user = user_id.strip()
    # 填了 QQ 就只看这个人
    if user:
        clauses.append("user_id = ?")
        args.append(user)
    code = reason_code.strip()
    # 填了原因码就只看这一类命中
    if code:
        clauses.append("reason_code = ?")
        args.append(code)
    # 三项都空就是整表
    if not clauses:
        return "", args
    return " WHERE " + " AND ".join(clauses), args


def _row_to_log(row: tuple) -> ForbiddenLog:
    """把查询行转成实体。"""
    return ForbiddenLog(
        int(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        str(row[7]),
        str(row[8]),
        str(row[9]),
    )
