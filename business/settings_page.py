# 业务层：插件 Pages 全局配置。校验通过后写进 rules.db 的 plugin_setting。
# 官方插件配置页字段全部 invisible，只在 Pages 改；schema 只在空表时导入一次。

from ..entity.constants import (
    SETTING_BOOL_KEYS,
    SETTING_INT_KEYS,
    SETTING_LIST_KEYS,
    SETTING_TEXT_KEYS,
)

# 18 个配置键按存储类型分组，和 data/setting_store.py 编解码用的是同一份定义。
# 名单按条添加，文本原样，整数是秒数，布尔是文本路规则开关。
_LIST_KEYS = SETTING_LIST_KEYS
_TEXT_KEYS = SETTING_TEXT_KEYS
_INT_KEYS = SETTING_INT_KEYS
_BOOL_KEYS = SETTING_BOOL_KEYS


def get_settings(config: object) -> dict:
    """读出当前字段。打开页必须是 schema 当前值。"""

    result = {}
    for key in _LIST_KEYS:
        result[key] = _read_list(config, key)
    for key in _TEXT_KEYS:
        result[key] = _read_text(config, key)
    for key in _INT_KEYS:
        result[key] = _read_int(config, key)
    for key in _BOOL_KEYS:
        result[key] = _read_bool(config, key)
    return result



async def save_settings(store, payload: dict) -> tuple[bool, str]:
    """校验后写进 plugin_setting。没带的键不覆盖库里的旧值。"""
    # 没挂配置存储就写不回去
    if store is None:
        return False, "没有插件配置。"
    parsed, error = _parse_payload(payload)
    # 某一项不合法整份不写，避免写一半
    if error:
        return False, error
    for key, value in parsed.items():
        await store.set_value(key, value)
    return True, "已保存。"


def _parse_payload(payload: dict) -> tuple[dict, str]:
    """只收下已知键。"""

    parsed = {}
    for key in _LIST_KEYS:
        # 没带这个键就保持原值
        if key not in payload:
            continue
        parsed[key] = _parse_list(payload.get(key))
    for key in _TEXT_KEYS:
        if key not in payload:
            continue
        parsed[key] = str(payload.get(key) or "")
    for key in _INT_KEYS:
        if key not in payload:
            continue
        number, error = _parse_int(payload.get(key))
        # 秒数不是整数就不写
        if error:
            return {}, error
        parsed[key] = number
    for key in _BOOL_KEYS:
        # 没带这个开关就保持原值
        if key not in payload:
            continue
        parsed[key] = _parse_bool(payload.get(key))
    return parsed, ""



def _parse_list(value: object) -> list:
    """名单收成去空白的字符串列表。字符串按换行拆。"""
    items = []
    # 页面用标签输入时是数组
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.splitlines()
    result = []
    for item in items:
        text = str(item).strip()
        # 空行丢掉，避免误开
        if not text:
            continue
        result.append(text)
    return result


def _parse_int(value: object) -> tuple[int, str]:
    """秒数收成整数。坏值报错。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0, "秒数必须是整数。"
    # 负数没有业务意义
    if number < 0:
        return 0, "秒数不能是负数。"
    return number, ""


def _read_list(config: object, key: str) -> list:
    """读名单。不是列表就空。"""
    value = _config_get(config, key)
    # 官方页按条添加才是列表
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        result.append(text)
    return result


def _read_text(config: object, key: str) -> str:
    """读文本。没有就空串。"""
    value = _config_get(config, key)
    # None 当没填
    if value is None:
        return ""
    return str(value)


def _read_int(config: object, key: str) -> int:
    """读整数。坏值当 0。"""
    value = _config_get(config, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_bool(config: object, key: str) -> bool:
    """读开关。缺字段或假值都关。"""
    return _parse_bool(_config_get(config, key))


def _parse_bool(value: object) -> bool:
    """只认明确打开。"""
    # 页面勾选、官方页 bool、偶发 1/true
    if value is True or value == 1 or value == "true":
        return True
    return False



def _config_get(config: object, key: str):
    """从配置取原值。"""
    if config is None:
        return None
    getter = getattr(config, "get", None)
    if not callable(getter):
        return None
    return getter(key)

