# 业务层：管理员用自然语言增删查黑名单。不踢人，不改群员身份。

from ..data.blacklist_store import BlacklistStore
from ..entity.constants import BLACKLIST_GLOBAL_SCOPE
from .auth import is_admin

REJECT_MESSAGE = "只有机器人的管理员能管理黑名单"


def clean_user_id(user_id: str) -> tuple[str, str]:
    """去掉空白，只接受纯数字 QQ 号。"""
    text = user_id.strip()
    # 空内容没法写入名单
    if not text:
        return "", "请提供 QQ 号。"
    # 旧模块也只收数字，避免把昵称写进库
    if not text.isdigit():
        return "", "QQ 号必须是数字。"
    return text, ""


def _list_name(group_id: str) -> str:
    """回报文案里区分本群名单和全局名单。"""
    # 全局名单的 group_id 是固定键，不是真实群号
    if group_id == BLACKLIST_GLOBAL_SCOPE:
        return "全局黑名单"
    return "本群黑名单"


async def add_user(
    store: BlacklistStore, event: object, group_id: str, user_id: str
) -> str:
    """把一个人写进指定名单。已在名单里不重复写。"""
    # 权限在业务层强制检查，不能依赖模型是否展示工具
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_user_id(user_id)
    # 号码不合法时不访问数据库
    if error:
        return error
    added = await store.add(group_id, clean)
    name = _list_name(group_id)
    # 已经在了要如实说，不能报成功
    if not added:
        return f"已经在{name}里：{clean}"
    return f"已加入{name}：{clean}"


async def delete_user(
    store: BlacklistStore, event: object, group_id: str, user_id: str
) -> str:
    """从指定名单删掉一个人。只删这一张名单。"""
    # 非管理员不能删库
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_user_id(user_id)
    # 空号和乱码不拿去查库
    if error:
        return error
    removed = await store.remove(group_id, clean)
    name = _list_name(group_id)
    # 没删到行必须如实回报
    if not removed:
        return f"不在{name}里：{clean}"
    return f"已从{name}移除：{clean}"


def list_users(store: BlacklistStore, event: object, group_id: str) -> str:
    """列出指定名单。非管理员不能看。"""
    # 查询也属于管理能力
    if not is_admin(event):
        return REJECT_MESSAGE
    ids = store.list_user_ids(group_id)
    name = _list_name(group_id)
    # 空名单用一句明确文案结束
    if not ids:
        return f"{name}是空的。"
    lines = [f"{name}（{len(ids)} 人）："]
    lines.extend(ids)
    return "\n".join(lines)
