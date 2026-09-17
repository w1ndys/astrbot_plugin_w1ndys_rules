# 业务层：人退群或被踢时清掉 pending。不发群消息，不调 OneBot。
# 判定方式和入群一样：读 raw_message.notice_type。

from ..data.verify_store import VerifyStore


def is_group_decrease(event: object) -> bool:
    """当前事件是不是 OneBot 的群成员减少通知。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就不是退群通知
    if obj is None:
        return False
    raw = getattr(obj, "raw_message", None)
    # 普通群消息和测试页没有 notice
    if raw is None:
        return False
    notice = _field(raw, "notice_type")
    return notice == "group_decrease"


async def drop_pending(store: VerifyStore, group_id: str, user_id: str) -> bool:
    """有 pending 就删行。没有行返回 False。"""
    # 没有 QQ 号对不上 pending
    if not user_id:
        return False
    code = store.get_code(group_id, user_id)
    # 不是待验证的人，退群也不用动库
    if not code:
        return False
    await store.delete(group_id, user_id)
    return True


def _field(raw: object, key: str) -> str:
    """从 OneBot Event 或 dict 取一个字段。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp Event 和 dict 都有 get
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(raw, key, "") or "")
