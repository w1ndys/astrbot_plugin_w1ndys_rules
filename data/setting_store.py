# 数据层：插件全局配置存 SQLite plugin_setting。
#
# schema（_conf_schema.json）只留着让 AstrBot 加载插件，并且只在空表时导入一次；
# 之后 Pages 保存和热路径都读这张表。名单存 JSON 数组，文本原样，整数十进制，
# 布尔只写 "1" / "0"，分组见 entity/constants.py 的 SETTING_*_KEYS。

import asyncio
import json
from pathlib import Path

from ..entity.constants import (
    SETTING_BOOL_KEYS,
    SETTING_FALSE,
    SETTING_INT_KEYS,
    SETTING_LIST_KEYS,
    SETTING_TEXT_KEYS,
    SETTING_TRUE,
)
from .db import connect, create_table

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plugin_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def _all_keys() -> tuple:
    """18 个配置键，按名单、文本、整数、布尔拼起来。导入时一个都不能漏。"""
    return SETTING_LIST_KEYS + SETTING_TEXT_KEYS + SETTING_INT_KEYS + SETTING_BOOL_KEYS


def _decode_list(raw):
    """把名单列解成字符串列表。缺行、坏数据、不是数组都当空。"""
    # 缺行就是空名单，不回退去读 schema
    if raw is None:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        # 坏数据当空名单，不能让页面报错
        return []
    # 只认数组，别的形状都不是名单
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        text = str(item).strip()
        # 空项丢掉，避免把空白当成群号
        if not text:
            continue
        result.append(text)
    return result


def _decode_text(raw) -> str:
    """文本原样返回。缺行当空串。"""
    # 缺行就是没填
    if raw is None:
        return ""
    return str(raw)


def _decode_int(raw) -> int:
    """整数是十进制字符串。缺行和坏值都当 0。"""
    # 缺行就是 0
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        # 坏数据当 0，页面还能继续保存
        return 0


def _decode_bool(raw) -> bool:
    """布尔只有 "1" 算开。缺行和别的值都当关。"""
    return raw == SETTING_TRUE


def _encode_list(value: object) -> list:
    """名单收成去空白的字符串列表。页面传字符串时按换行拆。"""
    items = []
    # 页面按条添加时是数组
    if isinstance(value, list):
        items = value
    # 也兼容换行分隔的文本框
    elif isinstance(value, str):
        items = value.splitlines()
    result = []
    for item in items:
        text = str(item).strip()
        # 空行丢掉，避免误开功能
        if not text:
            continue
        result.append(text)
    return result


def _encode_int(value: object) -> int:
    """整数收成 int。坏值当 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        # 坏值当 0，别把整行写成乱码
        return 0


def _encode_value(key: str, value: object) -> str:
    """按分组把值编成库里的文本。"""
    # 名单存 JSON 数组，中文不转义
    if key in SETTING_LIST_KEYS:
        return json.dumps(_encode_list(value), ensure_ascii=False)
    # 秒数等整数存十进制字符串
    if key in SETTING_INT_KEYS:
        return str(_encode_int(value))
    # 布尔只写 1 或 0
    if key in SETTING_BOOL_KEYS:
        # 明确为真才写 1，其余都当关
        if value:
            return SETTING_TRUE
        return SETTING_FALSE
    # 剩下的都是文本，空值当空串
    if value is None:
        return ""
    return str(value)


class SettingStore:
    """插件配置表。一个键一行，值统一是文本，按分组编解码。"""

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

    def count(self) -> int:
        """表里有多少行。用来判断 schema 还要不要导入。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM plugin_setting").fetchone()
        finally:
            conn.close()
        # COUNT(*) 总会回一行，拿不到就当 0
        if row is None:
            return 0
        return int(row[0])

    def get_value(self, key: str):
        """读一个键的原始文本。没有这一行返回 None。"""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM plugin_setting WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        # 缺行返回 None，由解码函数填类型空值
        if row is None:
            return None
        return str(row[0])

    async def set_value(self, key: str, value: object) -> None:
        """写一个键。已有这一行就覆盖值。"""
        async with self._lock:
            await asyncio.to_thread(self._set_sync, key, value)

    def _set_sync(self, key: str, value: object) -> None:
        """同步写入。值在这里编成文本。"""
        text = _encode_value(key, value)
        conn = connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO plugin_setting(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, text),
            )
            conn.commit()
        finally:
            conn.close()

    def load_dict(self) -> dict:
        """把 18 个键读成和 get_settings 一样形状的字典。缺行用类型对应的空值。"""
        result = {}
        for key in SETTING_LIST_KEYS:
            result[key] = _decode_list(self.get_value(key))
        for key in SETTING_TEXT_KEYS:
            result[key] = _decode_text(self.get_value(key))
        for key in SETTING_INT_KEYS:
            result[key] = _decode_int(self.get_value(key))
        for key in SETTING_BOOL_KEYS:
            result[key] = _decode_bool(self.get_value(key))
        return result

    def import_if_empty(self, settings: dict) -> None:
        """空表才把 schema 值搬进库。已经有行就直接返回，不覆盖 Pages 改过的值。"""
        # 库里有配置，schema 不再参与
        if self.count() > 0:
            return
        data = settings or {}
        # 18 个键全部写入，包括空值，保证导入后表不是空的
        for key in _all_keys():
            self._set_sync(key, data.get(key))
