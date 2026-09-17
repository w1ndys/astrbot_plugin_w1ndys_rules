# 业务层：群成员增加时要不要发欢迎语、发哪句。不碰 AstrBot 发送。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.welcome_store import WelcomeStore
from ..entity.constants import DEFAULT_WELCOME_TEXT, FEATURE_WELCOME


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


def pick_welcome(
    welcome: WelcomeStore, switches: GroupSwitchStore, group_id: str
) -> str:
    """开关关闭返回空串，不发。没设文案用默认句。"""
    # 默认关，没开过的群保持安静
    if not switches.is_on(group_id, FEATURE_WELCOME):
        return ""
    content = welcome.get_content(group_id)
    # 管理员只开了开关、还没写文案
    if not content:
        return DEFAULT_WELCOME_TEXT
    return content


def _field(raw: object, key: str) -> str:
    """从 OneBot Event 或 dict 取一个字段。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp Event 和 dict 都有 get
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(raw, key, "") or "")
