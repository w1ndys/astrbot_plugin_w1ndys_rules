# 业务层：从 OneBot 原始消息读发言人在本群的角色。
# AstrBot 的 MessageMember 没有 role，不能问 event.sender.role。

from ..entity.constants import QQ_ROLE_ADMIN, QQ_ROLE_OWNER


def speaker_qq_role(event: object) -> str:
    """取发言人的 OneBot role。没有原始消息或没有 role 时返回空串。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就读不到 sender
    if obj is None:
        return ""
    raw = getattr(obj, "raw_message", None)
    # 测试页和残缺事件没有 raw_message
    if raw is None:
        return ""
    sender = _sender_of(raw)
    return _role_of(sender)


def is_qq_group_staff(event: object) -> bool:
    """发言人是不是本群群主或管理员。读不到角色就当不是，继续检测。"""
    role = speaker_qq_role(event).casefold()
    # 群主默认安全，不送违禁模型
    if role == QQ_ROLE_OWNER:
        return True
    # 管理员同样跳过
    if role == QQ_ROLE_ADMIN:
        return True
    return False


def _sender_of(raw: object) -> object:
    """从 OneBot Event 或 dict 里取出 sender。"""
    sender = getattr(raw, "sender", None)
    # aiocqhttp 的 Event 带 sender 属性
    if sender is not None:
        return sender
    getter = getattr(raw, "get", None)
    # 普通 dict 走 get
    if callable(getter):
        return getter("sender")
    return None


def _role_of(sender: object) -> str:
    """从 sender 取出 role 字符串。"""
    # 原始消息里没有 sender
    if sender is None:
        return ""
    # OneBot sender 一般是 dict
    if isinstance(sender, dict):
        return str(sender.get("role") or "")
    return str(getattr(sender, "role", "") or "")
