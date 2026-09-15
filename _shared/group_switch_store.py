# _shared 数据层：本插件内每个功能在每个群的开关。不是跨插件公共模块。
#
# 约定「群默认关」：表里查不到记录就当关闭，所以机器人刚进一个新群时
# 不会自己开始发东西，要管理员显式打开。
#
# 这个判断在热路径上（每条群消息都要问一次），所以启动时把开着的开关
# 整表读进内存，群里发消息只查内存；写的时候先落库再改内存。

import asyncio
from pathlib import Path

from .db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS group_feature_switch (
    group_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, feature)
)
"""


class GroupSwitchStore:
    """群开关表。SQLite 负责长期保存，内存集合负责每条消息的快速判断。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        # 内存快照：只装「开着的」开关。没在里面的就是关闭，默认即关。
        self._on: set[tuple[str, str]] = set()
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
        """把开着的开关读进内存。关闭状态的群不占内存。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, feature FROM group_feature_switch WHERE enabled = 1"
            ).fetchall()
        finally:
            conn.close()
        self._on = {(str(row[0]), str(row[1])) for row in rows}

    def is_on(self, group_id: str, feature: str) -> bool:
        """本群这个功能开没开。只查内存，供每条群消息调用。"""
        return (group_id, feature) in self._on

    async def set_on(self, group_id: str, feature: str, enabled: bool) -> None:
        """改开关。先落库再改内存，落库失败就整条不算数。"""
        async with self._lock:
            await asyncio.to_thread(self._set_on_sync, group_id, feature, enabled)
        # 库确实写成功了才动内存，避免内存和库对不上
        if enabled:
            self._on.add((group_id, feature))
        else:
            self._on.discard((group_id, feature))

    def _set_on_sync(self, group_id: str, feature: str, enabled: bool) -> None:
        """同步写库，给 to_thread 用。REPLACE 让同一群同一功能只有一行。"""
        conn = connect(self.db_path)
        try:
            conn.execute(
                "REPLACE INTO group_feature_switch(group_id, feature, enabled) VALUES (?, ?, ?)",
                (group_id, feature, 1 if enabled else 0),
            )
            conn.commit()
        finally:
            conn.close()
