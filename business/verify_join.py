# 业务层：入群时要不要建 pending、验证说明怎么写。不发消息，不禁言，不碰 AstrBot。

import random

from .._shared.group_switch_store import GroupSwitchStore
from ..data.verify_store import VerifyStore
from ..entity.constants import FEATURE_VERIFY, VERIFY_CODE_LEN


def new_code(store: VerifyStore, group_id: str) -> str:
    """生成本群当前未占用的 6 位数字码。"""
    limit = 10**VERIFY_CODE_LEN
    while True:
        code = f"{random.randint(0, limit - 1):0{VERIFY_CODE_LEN}d}"
        # 本群已有人用这个码就换一个，避免两人复制同一条误通过
        if not store.code_in_use(group_id, code):
            return code


def hint_text(code: str) -> str:
    """入群验证说明。必须含码本身，复制整条私聊也能交码。"""
    return (
        "请私聊机器人发送包含验证码的消息完成人机验证。\n"
        f"验证码：{code}"
    )


async def start_pending(
    store: VerifyStore,
    switches: GroupSwitchStore,
    group_id: str,
    user_id: str,
    self_id: str = "",
) -> str:
    """开关开且不是机器人自己，才写 pending 并返回验证说明；否则空串。"""
    # 默认关，没开过的群不建码
    if not switches.is_on(group_id, FEATURE_VERIFY):
        return ""
    # 没有 QQ 号对不上人，不能建 pending
    if not user_id:
        return ""
    # 机器人自己入群不验证
    if self_id and user_id == self_id:
        return ""
    code = new_code(store, group_id)
    await store.put(group_id, user_id, code)
    return hint_text(code)
