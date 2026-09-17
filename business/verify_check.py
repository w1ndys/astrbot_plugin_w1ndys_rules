# 业务层：群消息里有没有待验证码、未通过要禁多久。不删 pending，不调 OneBot。

from ..entity.constants import (
    DEFAULT_VERIFY_MUTE_SECONDS,
    MAX_FORBIDDEN_MUTE_SECONDS,
    VERIFY_CFG_MUTE_SECONDS,
)


def code_in_text(text: str, code: str) -> bool:
    """消息文本是否包含这串码，且前后都不是数字。"""
    # 没有码就谈不上包含，空串会匹配任何位置
    if not code:
        return False
    start = 0
    while True:
        pos = text.find(code, start)
        # 后面再也找不到这串数字
        if pos < 0:
            return False
        # 前一个字符还是数字，说明嵌在更长的号码里，不能算交码
        if pos > 0 and text[pos - 1].isdigit():
            start = pos + 1
            continue
        end = pos + len(code)
        # 后一个字符还是数字，同样是更长号码的一段
        if end < len(text) and text[end].isdigit():
            start = pos + 1
            continue
        return True


def mute_seconds(config: object) -> int:
    """从 WebUI 取未通过禁言秒数。空值用默认，负数当 0，超过 QQ 上限就夹住。"""
    raw = _config_text(config, VERIFY_CFG_MUTE_SECONDS)
    # 没填就用 600 秒
    if not raw.strip():
        return DEFAULT_VERIFY_MUTE_SECONDS
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_VERIFY_MUTE_SECONDS
    # 0 表示这次不禁言；负数也当关掉惩罚
    if seconds < 0:
        return 0
    # QQ 单次最多 30 天
    if seconds > MAX_FORBIDDEN_MUTE_SECONDS:
        return MAX_FORBIDDEN_MUTE_SECONDS
    return seconds


def _config_text(config: object, key: str) -> str:
    """从插件配置里取字符串。没有配置或不是字符串时给空串。"""
    # 没挂上 WebUI 配置就当没填，用默认秒数
    if config is None:
        return ""
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当没有
    if not callable(getter):
        return ""
    value = getter(key)
    # None 当没填
    if value is None:
        return ""
    return str(value)
