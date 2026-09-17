# 业务层：其他管理员解开禁言时，待验证的人视为通过。
# 机器人自己解禁（交码通过、禁言到期）不算。不调 OneBot。


def is_admin_unmute(event: object, self_id: str) -> bool:
    """是不是别人把某个人解开禁言。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就不是通知
    if obj is None:
        return False
    raw = getattr(obj, "raw_message", None)
    # 普通群消息没有 notice
    if raw is None:
        return False
    # 禁言和解除都叫 group_ban，要看子类型
    if _field(raw, "notice_type") != "group_ban":
        return False
    # 只认解开，不认新禁言
    if _field(raw, "sub_type") != "lift_ban":
        return False
    operator = _field(raw, "operator_id")
    # 没有操作者、系统到期、机器人自己解，都不能当管理员通过
    if not operator or operator == "0" or operator == self_id:
        return False
    return True


def _field(raw: object, key: str) -> str:
    """从 OneBot Event 或 dict 取一个字段。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp Event 和 dict 都有 get
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(raw, key, "") or "")
