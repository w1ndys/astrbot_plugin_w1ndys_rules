# 业务层：到期该隔多久、白天窗口、怎么换新码，以及发新提醒并撤回上一条。

from datetime import datetime
from zoneinfo import ZoneInfo

from ..data.verify_store import VerifyStore
from ..entity.constants import (
    VERIFY_REMIND_HOUR_END,
    VERIFY_REMIND_HOUR_START,
    VERIFY_REMIND_INTERVAL_MINUTES,
)
from .verify_action import recall_message_id, send_verify_prompt
from .verify_join import hint_text, new_code

_BEIJING = ZoneInfo("Asia/Shanghai")


def remind_wait_minutes() -> int:
    """固定间隔 2 小时。"""
    return VERIFY_REMIND_INTERVAL_MINUTES


def in_remind_hours(now_ts: int) -> bool:
    """北京时间 8 点到 22 点才提醒。含 8 点，不含 22 点。"""
    hour = datetime.fromtimestamp(now_ts, _BEIJING).hour
    # 8 点前是夜里，不发
    if hour < VERIFY_REMIND_HOUR_START:
        return False
    # 22 点起算夜里，不发
    if hour >= VERIFY_REMIND_HOUR_END:
        return False
    return True


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
    wait = remind_wait_minutes()
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
    """到期发新提醒并撤回上一条。夜里、没到期或不是 pending 返回空串。"""
    # 夜里不换码、不发、不撤，等到白天再处理到期行
    if not in_remind_hours(now_ts):
        return ""
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
