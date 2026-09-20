# 数据层：每个群每个待验证人一行。通过、拒绝、退群就删行，不留历史状态。
#
# 每条群消息都要问「这个人待验证没有、码是多少」，所以启动时把整表读进内存。
# 不判断开关，不生成验证码，不碰 AstrBot。

import asyncio
import time
from datetime import datetime
from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.constants import VERIFY_REMIND_FIRST_MINUTES

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_pending (
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prompt_message_id TEXT NOT NULL DEFAULT '',
    next_remind_at INTEGER NOT NULL DEFAULT 0,
    remind_count INTEGER NOT NULL DEFAULT 0,
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
        # 入群提示消息 ID，通过后用来撤回。没有就空串。
        self._prompt_ids: dict[tuple[str, str], str] = {}
        # 下次群内提醒的 unix 秒。0 表示旧行还没排过期。
        self._next_remind: dict[tuple[str, str], int] = {}
        # 已发出的群内提醒次数。入群时 0，用来算下一档间隔。
        self._remind_counts: dict[tuple[str, str], int] = {}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()
        self._load_snapshot()

    def _setup(self) -> None:
        """首次启动时建表。旧库补提示消息列和提醒调度列。"""
        conn = connect(self.db_path)
        try:
            create_table(conn, CREATE_TABLE_SQL)
            self._ensure_prompt_column(conn)
            self._ensure_remind_columns(conn)
        finally:
            conn.close()

    def _table_columns(self, conn: object) -> list[str]:
        """当前 pending 表有哪些列。给旧库补列用。"""
        rows = conn.execute("PRAGMA table_info(verify_pending)").fetchall()
        return [str(row[1]) for row in rows]

    def _ensure_prompt_column(self, conn: object) -> None:
        """旧表没有提示消息列时补上，避免读列失败。"""
        names = self._table_columns(conn)
        # 新库建表时已经有这一列
        if "prompt_message_id" in names:
            return
        conn.execute(
            "ALTER TABLE verify_pending "
            "ADD COLUMN prompt_message_id TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()

    def _ensure_remind_columns(self, conn: object) -> None:
        """旧表没有提醒调度列时补上，避免读列失败。"""
        names = self._table_columns(conn)
        # 缺下次提醒时间就补 0，旧 pending 启动后会立刻到期
        if "next_remind_at" not in names:
            conn.execute(
                "ALTER TABLE verify_pending "
                "ADD COLUMN next_remind_at INTEGER NOT NULL DEFAULT 0"
            )
        # 缺次数就当还没提醒过
        if "remind_count" not in names:
            conn.execute(
                "ALTER TABLE verify_pending "
                "ADD COLUMN remind_count INTEGER NOT NULL DEFAULT 0"
            )
        conn.commit()

    def _load_snapshot(self) -> None:
        """把整张表读进内存。空码当没有这条，避免把人误判成待验证。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, user_id, code, prompt_message_id, "
                "next_remind_at, remind_count "
                "FROM verify_pending"
            ).fetchall()
        finally:
            conn.close()
        codes: dict[tuple[str, str], str] = {}
        prompts: dict[tuple[str, str], str] = {}
        next_remind: dict[tuple[str, str], int] = {}
        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            code = str(row[2])
            # 坏数据没有码，不能拿来判定包含匹配
            if not code:
                continue
            key = (str(row[0]), str(row[1]))
            codes[key] = code
            prompts[key] = str(row[3] or "")
            next_remind[key] = int(row[4] or 0)
            count = int(row[5] or 0)
            # 坏数据负数当没提醒过
            if count < 0:
                count = 0
            counts[key] = count
        self._codes = codes
        self._prompt_ids = prompts
        self._next_remind = next_remind
        self._remind_counts = counts

    def get_code(self, group_id: str, user_id: str) -> str:
        """取这个人在本群的待验证码。不是 pending 返回空串。"""
        code = self._codes.get((group_id, user_id))
        # 没行就不是待验证
        if code is None:
            return ""
        return code

    def get_prompt_message_id(self, group_id: str, user_id: str) -> str:
        """取入群验证提示的消息 ID。没有就空串。"""
        return self._prompt_ids.get((group_id, user_id), "")

    def get_next_remind_at(self, group_id: str, user_id: str) -> int:
        """下次群内提醒的 unix 秒。不是 pending 返回 0。"""
        return self._next_remind.get((group_id, user_id), 0)

    def get_remind_count(self, group_id: str, user_id: str) -> int:
        """已发出的群内提醒次数。不是 pending 返回 0。"""
        return self._remind_counts.get((group_id, user_id), 0)

    def list_due(self, now_ts: int) -> list[tuple[str, str]]:
        """到期该提醒的人。每项是 (群号, QQ)，按群号再按 QQ 排。"""
        due: list[tuple[str, str]] = []
        for key, next_at in self._next_remind.items():
            # 还没到点的人这次不提醒
            if next_at > now_ts:
                continue
            due.append(key)
        due.sort()
        return due

    def list_by_user(self, user_id: str) -> list[tuple[str, str, str]]:
        """这个人所有待验证群。每项是 (群号, 码, 提示消息 ID)，按群号排。"""
        rows: list[tuple[str, str, str]] = []
        for (gid, uid), code in self._codes.items():
            # 只收这个人，别的 QQ 的 pending 不参与私聊匹配
            if uid != user_id:
                continue
            prompt = self._prompt_ids.get((gid, uid), "")
            rows.append((gid, code, prompt))
        rows.sort(key=lambda item: item[0])
        return rows

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
        next_at = int(time.time()) + VERIFY_REMIND_FIRST_MINUTES * 60
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO verify_pending("
                "group_id, user_id, code, created_at, prompt_message_id, "
                "next_remind_at, remind_count"
                ") VALUES (?, ?, ?, ?, '', ?, 0) "
                "ON CONFLICT(group_id, user_id) DO UPDATE SET "
                "code = excluded.code, created_at = excluded.created_at, "
                "prompt_message_id = '', "
                "next_remind_at = excluded.next_remind_at, "
                "remind_count = 0",
                (group_id, user_id, code, stamp, next_at),
            )
            conn.commit()
        finally:
            conn.close()
        key = (group_id, user_id)
        self._codes[key] = code
        self._prompt_ids[key] = ""
        self._next_remind[key] = next_at
        self._remind_counts[key] = 0

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
        key = (group_id, user_id)
        self._codes.pop(key, None)
        self._prompt_ids.pop(key, None)
        self._next_remind.pop(key, None)
        self._remind_counts.pop(key, None)

    async def set_prompt_message_id(
        self, group_id: str, user_id: str, message_id: str
    ) -> None:
        """记下入群验证提示的消息 ID。没有 pending 就不写。"""
        async with self._lock:
            await asyncio.to_thread(
                self._set_prompt_sync, group_id, user_id, message_id
            )

    def _set_prompt_sync(
        self, group_id: str, user_id: str, message_id: str
    ) -> None:
        """同步写下提示消息 ID，给 to_thread 用。"""
        # 没有 pending 不能只写消息 ID
        if (group_id, user_id) not in self._codes:
            return
        conn = connect(self.db_path)
        try:
            conn.execute(
                "UPDATE verify_pending SET prompt_message_id = ? "
                "WHERE group_id = ? AND user_id = ?",
                (message_id, group_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()
        self._prompt_ids[(group_id, user_id)] = message_id

    async def update_remind(
        self,
        group_id: str,
        user_id: str,
        code: str,
        next_at: int,
        remind_count: int,
    ) -> None:
        """换新码、记下已提醒次数并排下次。没有 pending 就不写。"""
        async with self._lock:
            await asyncio.to_thread(
                self._update_remind_sync,
                group_id,
                user_id,
                code,
                next_at,
                remind_count,
            )

    def _update_remind_sync(
        self,
        group_id: str,
        user_id: str,
        code: str,
        next_at: int,
        remind_count: int,
    ) -> None:
        """同步换码并改调度，给 to_thread 用。"""
        key = (group_id, user_id)
        # 没有 pending 不能只改提醒
        if key not in self._codes:
            return
        conn = connect(self.db_path)
        try:
            conn.execute(
                "UPDATE verify_pending SET code = ?, prompt_message_id = '', "
                "next_remind_at = ?, remind_count = ? "
                "WHERE group_id = ? AND user_id = ?",
                (code, next_at, remind_count, group_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()
        self._codes[key] = code
        self._prompt_ids[key] = ""
        self._next_remind[key] = next_at
        self._remind_counts[key] = remind_count
