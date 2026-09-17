# 数据层：每个群每个待验证人一行。通过、拒绝、退群就删行，不留历史状态。
#
# 每条群消息都要问「这个人待验证没有、码是多少」，所以启动时把整表读进内存。
# 不判断开关，不生成验证码，不碰 AstrBot。

import asyncio
from datetime import datetime
from pathlib import Path

from .._shared.db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_pending (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
)
"""


class VerifyStore:
    """待验证表。主键是群号加人，值为当前验证码。没有行就不是待验证。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        # 内存快照：键是 (群号, QQ)，值是验证码。没有就是已通过或从没进过。
        self._codes: dict[tuple[str, str], str] = {}
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
        """把整张表读进内存。空码当没有这条，避免把人误判成待验证。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, user_id, code FROM verify_pending"
            ).fetchall()
        finally:
            conn.close()
        codes: dict[tuple[str, str], str] = {}
        for row in rows:
            code = str(row[2])
            # 坏数据没有码，不能拿来判定包含匹配
            if not code:
                continue
            codes[(str(row[0]), str(row[1]))] = code
        self._codes = codes

    def get_code(self, group_id: str, user_id: str) -> str:
        """取这个人在本群的待验证码。不是 pending 返回空串。"""
        code = self._codes.get((group_id, user_id))
        # 没行就不是待验证
        if code is None:
            return ""
        return code

    def list_user_ids(self, group_id: str) -> list[str]:
        """本群待验证 QQ 号，按号排序。只读内存，给扫描用。"""
        users: list[str] = []
        for gid, uid in self._codes:
            # 只列这一群，别的群的 pending 不给扫描
            if gid == group_id:
                users.append(uid)
        users.sort()
        return users

    def code_in_use(self, group_id: str, code: str) -> bool:
        """本群是否已有人占用这个码。生成新码时避开。"""
        for (gid, _uid), existing in self._codes.items():
            # 别的群可以撞码，只防本群待验证重复
            if gid == group_id and existing == code:
                return True
        return False

    async def put(self, group_id: str, user_id: str, code: str) -> None:
        """写入或覆盖这个人的待验证码。再入群会换新码。"""
        async with self._lock:
            await asyncio.to_thread(self._put_sync, group_id, user_id, code)

    def _put_sync(self, group_id: str, user_id: str, code: str) -> None:
        """同步写库并更新快照，给 to_thread 用。"""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO verify_pending(group_id, user_id, code, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(group_id, user_id) DO UPDATE SET "
                "code = excluded.code, created_at = excluded.created_at",
                (group_id, user_id, code, stamp),
            )
            conn.commit()
        finally:
            conn.close()
        self._codes[(group_id, user_id)] = code

    async def delete(self, group_id: str, user_id: str) -> None:
        """删掉 pending。通过、拒绝、退群都走这里。本来没有也算成功。"""
        async with self._lock:
            await asyncio.to_thread(self._delete_sync, group_id, user_id)

    def _delete_sync(self, group_id: str, user_id: str) -> None:
        """同步删库并更新快照，给 to_thread 用。"""
        conn = connect(self.db_path)
        try:
            conn.execute(
                "DELETE FROM verify_pending WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()
        self._codes.pop((group_id, user_id), None)
