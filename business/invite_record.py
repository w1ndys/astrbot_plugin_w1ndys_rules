# 业务层：群成员增加时，把这条邀请边写进库。
#
# 每群一份 WebUI 名单，空名单即关，避免刚装插件就开始攒数据。
# approve（进群申请被管理员同意）拿不到真实邀请人，按用户决定记成审批管理员，
# 也就是 operator_id。拿不到 operator_id 或自己邀请自己时不记，宁可不写也不造假边。
# 不判断名单以外的事，不发消息，不碰 AstrBot。

import logging

from ..data.invite_store import InviteStore
from ..entity.constants import CFG_INVITE_GROUPS
from .feature_enable import feature_on

_log = logging.getLogger("astrbot_plugin_w1ndys_rules")
async def record_join(
    store: InviteStore,
    config: object,
    event: object,
    group_id: str,
    user_id: str,
    self_id: str = "",
) -> bool:
    """入群通知落一条邀请边。写了返回 True，没写返回 False。"""
    # 空名单即关，没写过的群不记
    if not feature_on(config, CFG_INVITE_GROUPS, group_id):
        return False
    # 没有 QQ 号对不上人，不记
    if not user_id:
        return False
    # 机器人自己入群不是邀请关系
    if self_id and user_id == self_id:
        return False
    raw = _raw_message(event)
    # 普通群消息、退群这些没有通知原始体
    if raw is None:
        return False
    inviter = _field(raw, "operator_id")
    # 系统拉群、扫码进群等拿不到邀请人，不断定关系
    if not inviter or inviter == "0":
        return False
    # 自己邀请自己（例如扫码）不算邀请边
    if inviter == user_id:
        return False
    await store.record(group_id, user_id, inviter, _field(raw, "sub_type"))
    _log.info("[rules] invite record group=%s user=%s inviter=%s", group_id, user_id, inviter)
    return True


def _raw_message(event: object) -> object:
    """取通知的原始数据。测试桩和普通消息没有就返回 None。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就不是入群通知
    if obj is None:
        return None
    return getattr(obj, "raw_message", None)


def _field(raw: object, key: str) -> str:
    """从 OneBot Event 或 dict 取一个字段。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp Event 和 dict 都有 get
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(raw, key, "") or "")
