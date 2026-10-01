# 业务层：群成员增加时要不要发欢迎语、发哪句。不碰 AstrBot 发送。
#
# 本群独立配置为空串则关闭，优先于 WebUI 开启名单。
# 没写过独立配置时，开启群用全局文案，全局没填用默认句。

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..data.welcome_store import WelcomeStore
from ..entity.constants import (
    CFG_WELCOME_GROUPS,
    CFG_WELCOME_TEXT,
    DEFAULT_WELCOME_TEXT,
    WELCOME_MAX_LEN,
)
from .feature_enable import feature_on


def is_group_increase(event: object) -> bool:
    """当前事件是不是 OneBot 的群成员增加通知。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就不是入群通知
    if obj is None:
        return False
    raw = getattr(obj, "raw_message", None)
    # 普通群消息和测试页没有 notice
    if raw is None:
        return False
    notice = _field(raw, "notice_type")
    return notice == "group_increase"


def pick_welcome(welcome: WelcomeStore, config: object, group_id: str) -> str:
    """本群空串关闭；名单外不发；没独立文案用全局，全局空用默认句。"""
    override = welcome.get_content(group_id)
    # 独立配置写成空：本群关闭，压过开启名单
    if override is not None and not override.strip():
        _log.info("[rules] welcome skip group=%s reason=empty_override", group_id)
        return ""
    # 空名单即关，没写过独立配置的群保持安静
    if not feature_on(config, CFG_WELCOME_GROUPS, group_id):
        _log.info("[rules] welcome skip group=%s reason=not_enabled", group_id)
        return ""
    # 有独立文案就用本群的，不再读全局
    if override is not None:
        return _clip(override.strip())
    text = _welcome_text(config)
    # 开启群没填全局文案，用默认欢迎
    if not text:
        return DEFAULT_WELCOME_TEXT
    return _clip(text)


def _clip(text: str) -> str:
    """超长截断，避免误贴整篇文章刷屏。"""
    # 没超上限原样发
    if len(text) <= WELCOME_MAX_LEN:
        return text
    return text[:WELCOME_MAX_LEN]


def _welcome_text(config: object) -> str:
    """从 WebUI 取出全局欢迎语。没有配置当没填。"""
    # 没挂上 WebUI 配置就当全空
    if config is None:
        return ""
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当没有
    if not callable(getter):
        return ""
    value = getter(CFG_WELCOME_TEXT)
    # 没填或不是字符串当没配
    if not isinstance(value, str):
        return ""
    return value.strip()


def _field(raw: object, key: str) -> str:
    """从 OneBot Event 或 dict 取一个字段。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp Event 和 dict 都有 get
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(raw, key, "") or "")
