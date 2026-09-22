# 业务层：到期该隔多久、白天窗口、怎么换新码，以及发新提醒并撤回上一条。

from datetime import datetime
from zoneinfo import ZoneInfo

from ..data.verify_store import VerifyStore
from ..entity.constants import (
    VERIFY_REMIND_HOUR_END,
    VERIFY_REMIND_HOUR_START,
    VERIFY_REMIND_INTERVAL_MINUTES,
    VERIFY_REMIND_MAX,
)
from .verify_action import (
    kick_user,
    recall_message_id,
    send_group_plain,
    send_verify_prompt,
)
from .verify_join import new_code

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


def remind_text(code: str, sent_count: int) -> str:
    """到期提醒文案。sent_count 是这次发出后的次数，后面写还剩几次。"""
    left = VERIFY_REMIND_MAX - sent_count
    # 次数异常时不要把剩余写成负数
    if left < 0:
        left = 0
    return (
        "请私聊我发送包含验证码的消息完成人机验证。\n"
        f"验证码：{code}\n"
        f"这是第 {sent_count} 次提醒，还有 {left} 次机会。"
        f"超过 {VERIFY_REMIND_MAX} 次仍未验证将被移出群。"
    )


def _pending_due(store: VerifyStore, group_id: str, user_id: str, now_ts: int) -> bool:
    """还在待验证且到了提醒点。没到点不能换码，也不能提前踢。"""
    # 已经通过或从没进过，这一拍不用管
    if not store.get_code(group_id, user_id):
        return False
    # 还没到点，码仍然有效
    if store.get_next_remind_at(group_id, user_id) > now_ts:
        return False
    return True


async def kick_if_remind_exhausted(
    store: VerifyStore,
    event: object,
    group_id: str,
    user_id: str,
    now_ts: int,
) -> bool:
    """已提醒满 4 次且到期：踢出并清 pending。没到踢人条件返回 False。"""
    # 夜里不踢，跟提醒窗口一样，等到白天再处理
    if not in_remind_hours(now_ts):
        return False
    # 没到期不能因为次数够了就提前踢
    if not _pending_due(store, group_id, user_id, now_ts):
        return False
    # 还没满 4 次，这一拍继续发提醒
    if store.get_remind_count(group_id, user_id) < VERIFY_REMIND_MAX:
        return False
    old_prompt = store.get_prompt_message_id(group_id, user_id)
    ok = await kick_user(event, group_id, user_id)
    # 踢失败就留着 pending，下一拍再试，避免人还在群里验证却没了
    if not ok:
        return True
    await store.delete(group_id, user_id)
    await recall_message_id(event, old_prompt)
    await send_group_plain(
        event,
        group_id,
        f"{user_id} 验证提醒已超过 {VERIFY_REMIND_MAX} 次，已移出群。",
    )
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
    """到期发新提醒并撤回上一条。满 4 次则踢出。夜里或没到期返回空串。"""
    # 夜里不换码、不发、不踢，等到白天再处理到期行
    if not in_remind_hours(now_ts):
        return ""
    # 已满 4 次就踢，不再发第 5 次码
    if await kick_if_remind_exhausted(store, event, group_id, user_id, now_ts):
        return ""
    old_prompt = store.get_prompt_message_id(group_id, user_id)
    code = await rotate_due_code(store, group_id, user_id, now_ts)
    # 没换到新码就不要发、不要撤
    if not code:
        return ""
    sent = store.get_remind_count(group_id, user_id)
    mid = await send_verify_prompt(
        event, user_id, remind_text(code, sent), group_id
    )
    await recall_message_id(event, old_prompt)
    # 没拿到新消息 ID 就空着，下次通过也撤不掉
    if mid:
        await store.set_prompt_message_id(group_id, user_id, mid)
    return code
