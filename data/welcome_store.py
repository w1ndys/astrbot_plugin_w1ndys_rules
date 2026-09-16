# 数据层：每个群一条入群欢迎语文案。不判断开关，不碰 AstrBot。
#
# 入群通知不常发，不必像关键词那样常驻整表快照；读的时候查库。
# 写仍加锁，避免两个管理员同时改同一群时互相覆盖写了一半。

import asyncio
from pathlib import Path

from .._shared.db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS welcome_text (
    group_id TEXT NOT NULL PRIMARY KEY,
    content TEXT NOT NULL
)
"""


class WelcomeStore:
    """入群欢迎语文案表。没有记录就当还没设置过，读出来是空串。"""

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

    def get_content(self, group_id: str) -> str:
        """取本群欢迎语。没设过返回空串，默认文案留给业务层。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT content FROM welcome_text WHERE group_id = ?",
                (group_id,),
            ).fetchone()
        finally:
            conn.close()
        # 这群还没写过欢迎语
        if row is None:
            return ""
        return str(row[0])

    async def set_content(self, group_id: str, content: str) -> None:
        """写入或覆盖本群欢迎语。写完立刻能读到。"""
        async with self._lock:
            await asyncio.to_thread(self._set_content_sync, group_id, content)

    def _set_content_sync(self, group_id: str, content: str) -> None:
        """同步写库，给 to_thread 用。同群只有一行。"""
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO welcome_text(group_id, content) VALUES (?, ?) "
                "ON CONFLICT(group_id) DO UPDATE SET content = excluded.content",
                (group_id, content),
            )
            conn.commit()
        finally:
            conn.close()
