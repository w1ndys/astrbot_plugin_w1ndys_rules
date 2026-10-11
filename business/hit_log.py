# 业务层：违禁命中那一刻打的一行日志。群号、发言人、原始 payload 都在同一行。
# payload 里的签名和 token 打码后才打，避免把密钥写进日志文件。

import json

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from .debug_payload import to_plain

# 字段名或查询参数名里出现这些片段就当密钥，命中就遮。宁可多遮不可漏遮。
_SENSITIVE_KEY_MARKERS = (
    "token",
    "sig",
    "sign",
    "secret",
    "password",
    "passwd",
    "key",
    "auth",
)
# 打码后的占位文字，日志里一眼能看出这里被遮过
_MASKED = "[已打码]"
# 事件里读不到原始包时用它顶替，日志里一眼能看出这次没采到
_EMPTY_PAYLOAD = "{}"


def hit_line(group_id: str, user_id: str, payload: str) -> str:
    """拼命中那一行：群号、发言人、原始 payload。"""
    return f"[群管] 违禁命中 群号={group_id} 发言人={user_id} payload={payload}"


def payload_text(event: object) -> str:
    """取这条消息的原始 payload，转成一行 JSON。签名和 token 打码，读不到给 {}。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就没有原始包可打
    if obj is None:
        return _EMPTY_PAYLOAD
    raw = getattr(obj, "raw_message", None)
    # 通知类以外的消息可能没有原始体
    if raw is None:
        return _EMPTY_PAYLOAD
    return json.dumps(mask_payload(to_plain(raw)), ensure_ascii=False, default=str)


def log_hit(group_id: str, user_id: str, event: object) -> None:
    """命中成功打一条 INFO。文本、二维码、图片转写、视频抽帧、联系人卡片都走这里。"""
    _log.info(hit_line(group_id, user_id, payload_text(event)))


def mask_payload(value: object) -> object:
    """递归给 payload 打码：字段名像密钥就遮值，地址里的签名参数也遮。"""
    # 字典逐项看字段名，命中的整段遮掉，不看内容
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            # 字段名像密钥就遮，否则继续往下钻
            if _is_sensitive_key(str(key)):
                result[key] = _MASKED
            else:
                result[key] = mask_payload(item)
        return result
    # 列表逐项递归，藏在列表里的签名也要遮
    if isinstance(value, list):
        result = []
        for item in value:
            result.append(mask_payload(item))
        return result
    # 字符串可能是带签名查询串的地址
    if isinstance(value, str):
        return mask_query(value)
    return value


def mask_query(text: str) -> str:
    """把地址查询串里的敏感参数值换成占位。不是带查询串的地址就原样返回。"""
    # 没有问号就没有查询串，也就不用遮
    if "?" not in text:
        return text
    head, _, query = text.partition("?")
    parts = []
    for pair in query.split("&"):
        name, sep, _rest = pair.partition("=")
        # 参数名像密钥就遮值，其余原样留着方便排查
        if sep and _is_sensitive_key(name):
            parts.append(name + "=" + _MASKED)
        else:
            parts.append(pair)
    return head + "?" + "&".join(parts)


def _is_sensitive_key(name: str) -> bool:
    """字段名或参数名里出现密钥类片段就算敏感。"""
    lower = name.lower()
    for marker in _SENSITIVE_KEY_MARKERS:
        # 命中任一标记就当密钥
        if marker in lower:
            return True
    return False
