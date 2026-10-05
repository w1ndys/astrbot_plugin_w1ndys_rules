# 业务层：从 OneBot 原始消息读发言人在本群的角色和群昵称。
# AstrBot 的 MessageMember 没有 role，不能问 event.sender.role。
# 群昵称也从同一个 sender 读：群名片优先，其次 QQ 昵称。
# display_name_of 是群昵称的唯一规则，命中写日志和旧日志回补都调它。

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


def speaker_display_name(event: object) -> str:
    """取发言人在本群的展示名，写进违禁日志的 sender_name 列。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就读不到 sender
    if obj is None:
        return ""
    raw = getattr(obj, "raw_message", None)
    # 测试页和残缺事件没有 raw_message
    if raw is None:
        return ""
    return _display_name_of(_sender_of(raw))


def display_name_of(card: str, nickname: str) -> str:
    """群名片优先，其次 QQ 昵称。命中写日志和旧日志回补都走这一条规则。"""
    clean_card = card.strip()
    # 群名片是成员在本群的展示名，优先用它
    if clean_card:
        return clean_card
    return nickname.strip()


def _display_name_of(sender: object) -> str:
    """从 sender 取群昵称。原始消息里没有 sender 就是空串。"""
    # 没有 sender 就没有名片也没有昵称
    if sender is None:
        return ""
    return display_name_of(_field_of(sender, "card"), _field_of(sender, "nickname"))


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
    return _field_of(sender, "role")


def _field_of(sender: object, key: str) -> str:
    """从 sender 取一个字符串字段。dict 走 get，对象走属性。"""
    # OneBot sender 一般是 dict
    if isinstance(sender, dict):
        return str(sender.get(key) or "")
    return str(getattr(sender, key, "") or "")
