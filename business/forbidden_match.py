# 业务层：违禁词触发词的包含匹配，以及网址/群号/QQ/手机/微信规则。
# 不进大模型，不处置。规则命中当作触发词。
#
# 触发词来自本群 SQLite。消息里包含任一触发词才算命中，英文不区分大小写，
# 中文按原文包含。规则开关在 WebUI，默认全关。

import re

from ..entity.constants import (
    FORBIDDEN_CFG_TRIGGER_GROUP,
    FORBIDDEN_CFG_TRIGGER_PHONE,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_URL,
    FORBIDDEN_CFG_TRIGGER_WECHAT,
    FORBIDDEN_PATTERN_GROUP,
    FORBIDDEN_PATTERN_PHONE,
    FORBIDDEN_PATTERN_QQ,
    FORBIDDEN_PATTERN_URL,
    FORBIDDEN_PATTERN_WECHAT,
)

# 网址：带协议、www，或常见域名。
_URL_RE = re.compile(
    r"(https?://[^\s]+)|"
    r"(www\.[^\s]+)|"
    r"(?<![@\w])[a-z0-9][-a-z0-9]{0,62}\."
    r"(?:com|cn|net|org|cc|xyz|top|vip|club|app|io|me|tv|co)"
    r"(?:/[^\s]*)?",
    re.I,
)
# 大陆手机号，前后不能再跟数字。
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 加群/群号后面的数字。
_GROUP_RE = re.compile(r"(?:加群|进群|群号|群)[:：\s]*[1-9]\d{4,9}")
# wxid_ 或「微信/wx」后面的账号。
_WECHAT_RE = re.compile(
    r"(wxid_[a-zA-Z0-9]+)|"
    r"(?:微信号?|(?<![a-zA-Z])wx(?![a-zA-Z])|v信|威信)[:：\s]*[a-zA-Z][a-zA-Z0-9_-]{5,19}",
    re.I,
)

# 5~11 位数字，后面再筛掉手机号和日期。
_DIGIT_RE = re.compile(r"(?<!\d)[1-9]\d{4,10}(?!\d)")

_PATTERN_KEYS = (
    FORBIDDEN_CFG_TRIGGER_URL,
    FORBIDDEN_CFG_TRIGGER_GROUP,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_PHONE,
    FORBIDDEN_CFG_TRIGGER_WECHAT,
)


def find_trigger(text: str, words: list) -> str:
    """在消息里找第一个命中的触发词。找不到返回空串。"""
    # 没有文本或没有词，不可能命中
    if not text or not words:
        return ""
    haystack = text.casefold()
    for word in words:
        needle = word.casefold()
        # 空白词不当触发词，避免空串包含在任何消息里
        if not needle:
            continue
        # 包含即命中，英文大小写已经折到同一套字符
        if needle in haystack:
            return word
    return ""


def flag_on(config: object, key: str) -> bool:
    """WebUI 开关是否打开。没配、不是真值都当关。"""
    # 没挂配置就全关，保持旧行为
    if config is None:
        return False
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当关
    if not callable(getter):
        return False
    value = getter(key)
    # 只认明确打开，缺字段不继承成开
    if value is True or value == 1 or value == "true":
        return True
    return False


def any_pattern_on(config: object) -> bool:
    """五个规则开关有没有打开的。"""
    for key in _PATTERN_KEYS:
        # 开了一个就可以不靠触发词表
        if flag_on(config, key):
            return True
    return False


def find_pattern_trigger(text: str, config: object) -> str:
    """按打开的规则找触发名。词表没命中时才用。"""
    # 空消息对不上规则
    if not text:
        return ""
    # 网址最直观，优先
    if flag_on(config, FORBIDDEN_CFG_TRIGGER_URL) and _URL_RE.search(text):
        return FORBIDDEN_PATTERN_URL
    # 11 位手机号
    if flag_on(config, FORBIDDEN_CFG_TRIGGER_PHONE) and _PHONE_RE.search(text):
        return FORBIDDEN_PATTERN_PHONE
    # 微信号或 wxid_
    if flag_on(config, FORBIDDEN_CFG_TRIGGER_WECHAT) and _WECHAT_RE.search(text):
        return FORBIDDEN_PATTERN_WECHAT
    # 加群/群号，避免和裸 QQ 号抢
    if flag_on(config, FORBIDDEN_CFG_TRIGGER_GROUP) and _GROUP_RE.search(text):
        return FORBIDDEN_PATTERN_GROUP
    # 剩下的 5~11 位数字当 QQ 号
    if flag_on(config, FORBIDDEN_CFG_TRIGGER_QQ) and _has_qq(text):
        return FORBIDDEN_PATTERN_QQ
    return ""


def _has_qq(text: str) -> bool:
    """有没有不像手机号、不像日期的 QQ 号。"""
    for match in _DIGIT_RE.finditer(text):
        token = match.group(0)
        # 11 位手机号留给手机开关
        if _PHONE_RE.fullmatch(token):
            continue
        # 20 开头的 8 位当日期，不当 QQ
        if len(token) == 8 and token.startswith("20"):
            continue
        return True
    return False
