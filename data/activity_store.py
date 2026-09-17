# 数据层：每个群每个人上次发言时间。不判断违禁，不碰 AstrBot。
#
# 每条有文本的群消息都要问「近 7 天发过言没有」，所以启动时把整张表读进内存。
# 刚装上表是空的，全员先当不活跃。

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.constants import ACTIVE_WINDOW_DAYS

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS last_speak (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
)
"""


class ActivityStore:
    """本群最后发言表。主键是群号加人，值为上次发言时间。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        # 内存快照：键是 (群号, QQ)，值是上次发言时间。没有就是从没记过。
        self._last: dict[tuple[str, str], datetime] = {}
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
        """把整张表读进内存。坏时间当没发过，下次发言会覆盖。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, user_id, last_seen FROM last_speak"
            ).fetchall()
        finally:
            conn.close()
        last: dict[tuple[str, str], datetime] = {}
        for row in rows:
            when = _parse_last_seen(str(row[2]))
            # 解析失败就当这条不存在，避免把全员判成活跃
            if when is None:
                continue
            last[(str(row[0]), str(row[1]))] = when
        self._last = last

    def is_within_window(self, group_id: str, user_id: str) -> bool:
        """这个人上次在本群发言是否还在 7 天窗口内。没记录当不活跃。"""
        when = self._last.get((group_id, user_id))
        # 从没记过，刚装上全员先当不活跃
        if when is None:
            return False
        delta = datetime.now() - when
        return delta <= timedelta(days=ACTIVE_WINDOW_DAYS)

    async def touch(self, group_id: str, user_id: str) -> None:
        """记下这个人现在在本群发过言。写完立刻能读到。"""
        async with self._lock:
            await asyncio.to_thread(self._touch_sync, group_id, user_id)

    def _touch_sync(self, group_id: str, user_id: str) -> None:
        """同步写库并更新快照，给 to_thread 用。"""
        when = datetime.now()
        stamp = when.strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO last_speak(group_id, user_id, last_seen) VALUES (?, ?, ?) "
                "ON CONFLICT(group_id, user_id) DO UPDATE SET last_seen = excluded.last_seen",
                (group_id, user_id, stamp),
            )
            conn.commit()
        finally:
            conn.close()
        self._last[(group_id, user_id)] = when


def _parse_last_seen(raw: str) -> datetime | None:
    """把库里的时间字符串解析成 datetime。格式不对返回 None。"""
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # 坏数据不当活跃，留给下次发言覆盖
        return None
