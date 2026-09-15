# _shared 数据层：rules 包内各功能共用的 SQLite 底座。
# 只放「怎么连库、怎么建表」这种每个功能都要重复一遍的代码，
# 表结构和业务 SQL 留在各自的 data/*_store.py 里。

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """打开一个 SQLite 连接。WAL 让读写不容易互相堵住。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def create_table(conn: sqlite3.Connection, create_sql: str) -> None:
    """按给定语句建表，表已存在就跳过。建完立刻提交，避免连接关掉时丢结构。"""
    conn.execute(create_sql)
    conn.commit()
