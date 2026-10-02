# 数据层：群号到群名的映射表。不调 OneBot，不碰 AstrBot。
# 读的时候查库；写加锁，避免两个管理员同时保存时互相覆盖写了一半。

import asyncio
from pathlib import Path

from ..entity.group_name import GroupName
from .db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS group_name (
    group_id TEXT NOT NULL PRIMARY KEY,
    group_name TEXT NOT NULL
)
"""


class GroupNameStore:
    """群名映射表。同一群号只有一行；没行表示还没保存过名字。"""

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

    def get_name(self, group_id: str) -> str:
        """取一个群的展示名。没行返回空串，页面显示空列。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT group_name FROM group_name WHERE group_id = ?",
                (group_id,),
            ).fetchone()
        finally:
            conn.close()
        # 这群还没保存过名字，三页都显示空
        if row is None:
            return ""
        return str(row[0])

    def list_all(self) -> list:
        """全部映射，按群号排。给 Pages 一次拉完做对照。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, group_name FROM group_name ORDER BY group_id"
            ).fetchall()
        finally:
            conn.close()
        items = []
        for group_id, group_name in rows:
            items.append(GroupName(str(group_id), str(group_name)))
        return items

    def as_map(self) -> dict:
        """群号到群名的字典。没保存过的群不会出现。"""
        result = {}
        for item in self.list_all():
            result[item.group_id] = item.group_name
        return result

    async def upsert(self, group_id: str, group_name: str) -> None:
        """写入或覆盖一个群的名字。空群号不写，避免脏主键。"""
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, group_id, group_name)

    async def upsert_many(self, items: list) -> None:
        """批量 upsert。协议没返回的旧行不删。"""
        async with self._lock:
            await asyncio.to_thread(self._upsert_many_sync, items)

    def _upsert_sync(self, group_id: str, group_name: str) -> None:
        """同步写一行，给 to_thread 用。"""
        # 空群号对不上任何功能名单，写进去也没用
        if not group_id:
            return
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO group_name(group_id, group_name) VALUES (?, ?) "
                "ON CONFLICT(group_id) DO UPDATE SET group_name = excluded.group_name",
                (group_id, group_name),
            )
            conn.commit()
        finally:
            conn.close()

    def _upsert_many_sync(self, items: list) -> None:
        """同一连接写多行再提交，协议没返回的旧行不删。"""
        conn = connect(self.db_path)
        try:
            for item in items:
                group_id = item.group_id
                # 空群号跳过，其余行继续写
                if not group_id:
                    continue
                conn.execute(
                    "INSERT INTO group_name(group_id, group_name) VALUES (?, ?) "
                    "ON CONFLICT(group_id) DO UPDATE SET "
                    "group_name = excluded.group_name",
                    (group_id, item.group_name),
                )
            conn.commit()
        finally:
            conn.close()
