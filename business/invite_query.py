# 业务层：管理员查本群邀请树上线和整条下线。不写库，不碰 AstrBot。

from ..data.invite_store import InviteStore
from ..entity.constants import INVITE_DOWNLINE_LIMIT, INVITE_UPLINE_LIMIT
from .auth import is_admin

REJECT_MESSAGE = "只有机器人的管理员能查询邀请树"


def clean_user_id(user_id: str) -> tuple[str, str]:
    """去掉空白，只接受纯数字 QQ 号。"""
    text = user_id.strip()
    # 空内容没法对上邀请边
    if not text:
        return "", "请提供 QQ 号。"
    # 只收数字，避免把昵称拿去查
    if not text.isdigit():
        return "", "QQ 号必须是数字。"
    return text, ""


def walk_upline(store: InviteStore, group_id: str, user_id: str) -> list[str]:
    """从本人往上追邀请人，直到没记录、成环或碰到层数上限。"""
    chain = [user_id]
    seen = {user_id}
    current = user_id
    while len(chain) < INVITE_UPLINE_LIMIT:
        edge = store.get_edge(group_id, current)
        # 没有邀请边，这条链到头了
        if edge is None:
            break
        nxt = edge.inviter_id
        # 缺邀请人或已经出现过，当成环截断
        if not nxt or nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
        current = nxt
    return chain


def walk_downline(
    store: InviteStore, group_id: str, user_id: str
) -> tuple[list[tuple[str, int]], int]:
    """广度优先列出整条下线。返回（要显示的人及深度, 下线总人数）。"""
    shown: list[tuple[str, int]] = []
    total = 0
    seen = {user_id}
    queue: list[tuple[str, int]] = [
        (child, 1) for child in store.list_direct_downline(group_id, user_id)
    ]
    while queue:
        uid, depth = queue.pop(0)
        # 成环或重复入队的人跳过，避免死循环
        if uid in seen:
            continue
        seen.add(uid)
        total += 1
        # 超出上限的人仍计入总数，但不写进回报
        if len(shown) < INVITE_DOWNLINE_LIMIT:
            shown.append((uid, depth))
        for child in store.list_direct_downline(group_id, uid):
            # 已经走过的人不再往下扩
            if child in seen:
                continue
            queue.append((child, depth + 1))
    return shown, total


def show_upline(store: InviteStore, event: object, group_id: str, user_id: str) -> str:
    """查出这个人在本群的上线链。"""
    # 查询也属于管理能力
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_user_id(user_id)
    # 号码不合法时不查库
    if error:
        return error
    chain = walk_upline(store, group_id, clean)
    # 只有本人、没有邀请边
    if len(chain) == 1:
        return f"本群没有 {clean} 的邀请记录"
    text = f"本群 {clean} 的上线：\n" + " ← ".join(chain)
    # 碰到层数上限时如实说截断了
    if len(chain) >= INVITE_UPLINE_LIMIT:
        return text + "\n（上线链过长，已截断）"
    return text


def show_downline(store: InviteStore, event: object, group_id: str, user_id: str) -> str:
    """查出这个人在本群的整条下线。"""
    # 查询也属于管理能力
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_user_id(user_id)
    # 号码不合法时不查库
    if error:
        return error
    shown, total = walk_downline(store, group_id, clean)
    # 一个人都没拉过
    if total == 0:
        return f"本群 {clean} 还没有下线"
    lines = [f"本群 {clean} 的下线（{total} 人）："]
    for uid, depth in shown:
        lines.append(("  " * (depth - 1)) + uid)
    # 超出上限只报数量
    if total > len(shown):
        rest = total - len(shown)
        lines.append(f"（只列出前 {INVITE_DOWNLINE_LIMIT} 人，其余 {rest} 人未显示）")
    return "\n".join(lines)
