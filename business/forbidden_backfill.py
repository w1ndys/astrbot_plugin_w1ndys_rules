# 业务层：违禁日志的群昵称回补。只拆协议字段、定规则和文案，不调 OneBot，不写 SQL。
# 协议结果由入口逐群拉取后传进来，和群名页的分工一致。

from ..data.forbidden_log_store import ForbiddenLogStore
from .qq_role import display_name_of


def pending_backfill_groups(store: ForbiddenLogStore) -> list[str]:
    """还留着空群昵称的群号。入口按这份清单逐群拉成员资料。"""
    return store.groups_with_empty_sender_name()


def member_names(raw: object) -> dict:
    """从 get_group_member_list 回报收成 {QQ: 群昵称}。填不了空值的成员不进这份表。"""
    names = {}
    for member in _member_rows(raw):
        # 不是一条成员资料就跳过
        if not isinstance(member, dict):
            continue
        user_id = str(member.get("user_id") or "").strip()
        # 没有 QQ 对不上日志行
        if not user_id:
            continue
        name = display_name_of(
            str(member.get("card") or ""), str(member.get("nickname") or "")
        )
        # 名片和昵称都空，这条资料填不了空昵称
        if not name:
            continue
        names[user_id] = name
    return names


async def backfill_group(store: ForbiddenLogStore, group_id: str, raw: object) -> int:
    """把这一群的成员资料填进空昵称行，返回写入条数。"""
    return await store.backfill_sender_names(group_id, member_names(raw))


def backfill_message(updated: int, failed: list) -> str:
    """回补结果的人话。有失败群就列出群号。"""
    # 全都补上，不用列失败群
    if not failed:
        return f"已回补 {updated} 条群昵称。"
    numbers = "、".join(str(item.get("group_id") or "") for item in failed)
    return f"已回补 {updated} 条群昵称；这些群失败：{numbers}。"


def _member_rows(raw: object) -> list:
    """取出成员资料数组。直接列表，或包在 data 里。"""
    # NapCat 有时直接回列表
    if isinstance(raw, list):
        return raw
    getter = getattr(raw, "get", None)
    # 不是对象就没有成员
    if not callable(getter):
        return []
    data = getter("data")
    # 常见是 {data: [...]}
    if isinstance(data, list):
        return data
    return []
