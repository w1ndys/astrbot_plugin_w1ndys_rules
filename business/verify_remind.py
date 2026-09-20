# 业务层：到期该隔多久、怎么换新码，以及发新提醒并撤回上一条。

from ..data.verify_store import VerifyStore
from ..entity.constants import VERIFY_REMIND_FIRST_MINUTES, VERIFY_REMIND_MAX_MINUTES
from .verify_action import recall_message_id, send_verify_prompt
from .verify_join import hint_text, new_code


def remind_wait_minutes(remind_count: int) -> int:
    """按已提醒次数算出这一档要等几分钟。入群时 0 → 2，之后 4、8、16，封顶 30。"""
    # 负数当没提醒过，避免坏数据算出 0 分钟狂刷
    if remind_count < 0:
        remind_count = 0
    minutes = VERIFY_REMIND_FIRST_MINUTES * (2 ** remind_count)
    # 超过上限就固定 30 分钟，不再翻倍
    if minutes > VERIFY_REMIND_MAX_MINUTES:
        return VERIFY_REMIND_MAX_MINUTES
    return minutes


async def rotate_due_code(
    store: VerifyStore, group_id: str, user_id: str, now_ts: int
) -> str:
    """到期换新码、次数加一、排下次。不是 pending 或没到点返回空串。"""
    old = store.get_code(group_id, user_id)
    # 已经通过或从没进过，不能换码
    if not old:
        return ""
    next_at = store.get_next_remind_at(group_id, user_id)
    # 还没到点不换，避免循环提前作废有效码
    if next_at > now_ts:
        return ""
    code = new_code(store, group_id)
    count = store.get_remind_count(group_id, user_id) + 1
    wait = remind_wait_minutes(count)
    await store.update_remind(
        group_id, user_id, code, now_ts + wait * 60, count
    )
    return code


async def send_due_remind(
    store: VerifyStore,
    event: object,
    group_id: str,
    user_id: str,
    now_ts: int,
) -> str:
    """到期发新提醒并撤回上一条。没到期或不是 pending 返回空串。"""
    old_prompt = store.get_prompt_message_id(group_id, user_id)
    code = await rotate_due_code(store, group_id, user_id, now_ts)
    # 没换到新码就不要发、不要撤
    if not code:
        return ""
    mid = await send_verify_prompt(event, user_id, hint_text(code), group_id)
    await recall_message_id(event, old_prompt)
    # 没拿到新消息 ID 就空着，下次通过也撤不掉
    if mid:
        await store.set_prompt_message_id(group_id, user_id, mid)
    return code
