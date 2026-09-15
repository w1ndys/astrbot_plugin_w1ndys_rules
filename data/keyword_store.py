# 数据层：关键词回复规则的 SQLite 存取。不判断权限，不碰 AstrBot。
#
# 命中判断在热路径上（每条群消息都要过一遍），所以启动时把整张表读进内存，
# SQLite 只作为持久化。管理员写入后由调用方重建快照。

from pathlib import Path

from .._shared.db import connect, create_table
from ..entity.keyword import KeywordRule

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS keyword_reply (
    group_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    reply TEXT NOT NULL,
    PRIMARY KEY (group_id, keyword)
)
"""


class KeywordStore:
    """关键词规则表。SQLite 负责长期保存，内存快照负责每条群消息的命中判断。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        # 内存快照：键是 (群号, 关键词)，值是整条规则。没在里面的就是没有这条关键词。
        self._snapshot: dict[tuple[str, str], KeywordRule] = {}
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
        """把整张表读进内存。群号不同、关键词相同的规则各存各的。"""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT group_id, keyword, reply FROM keyword_reply"
            ).fetchall()
        finally:
            conn.close()
        snapshot: dict[tuple[str, str], KeywordRule] = {}
        for row in rows:
            rule = KeywordRule(str(row[0]), str(row[1]), str(row[2]))
            snapshot[(rule.group_id, rule.keyword)] = rule
        self._snapshot = snapshot

    def find_reply(self, group_id: str, text: str) -> str:
        """按群号和整条消息文本查回复。完全匹配，查不到返回空串。"""
        rule = self._snapshot.get((group_id, text))
        # 没有这条关键词就没什么可回的
        if rule is None:
            return ""
        return rule.reply
