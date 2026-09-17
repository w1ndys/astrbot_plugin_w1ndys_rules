# 业务层：管理员通过、拒绝、扫描本群待验证的人。不踢人，不调 OneBot。
# 通过后入口再解禁；扫描的 QQ 列表留给入口去 @。

from ..data.verify_store import VerifyStore
from .auth import is_admin

REJECT_MESSAGE = "只有机器人的管理员能管理入群验证"


def _clean_user_id(user_id: str) -> tuple[str, str]:
    """去掉空白，只接受纯数字 QQ 号。"""
    text = user_id.strip()
    # 空内容对不上 pending
    if not text:
        return "", "请提供 QQ 号。"
    # 只收数字，避免把昵称写进库
    if not text.isdigit():
        return "", "QQ 号必须是数字。"
    return text, ""


async def pass_user(
    store: VerifyStore, event: object, group_id: str, user_id: str
) -> tuple[str, str]:
    """把待验证的人标通过并删行。返回 (文案, 需要解禁的 QQ)。没通过则 QQ 空串。"""
    # 权限在业务层强制检查，不能依赖模型是否展示工具
    if not is_admin(event):
        return REJECT_MESSAGE, ""
    clean, error = _clean_user_id(user_id)
    # 号码不合法时不访问数据库
    if error:
        return error, ""
    code = store.get_code(group_id, clean)
    # 没有 pending 不能假装通过
    if not code:
        return f"不在待验证名单里：{clean}", ""
    await store.delete(group_id, clean)
    return f"已通过入群验证：{clean}", clean


async def reject_user(
    store: VerifyStore, event: object, group_id: str, user_id: str
) -> str:
    """关掉这个人的 pending。不踢人。"""
    # 非管理员不能改验证状态
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = _clean_user_id(user_id)
    # 空号和乱码不拿去查库
    if error:
        return error
    code = store.get_code(group_id, clean)
    # 没这行要如实说
    if not code:
        return f"不在待验证名单里：{clean}"
    await store.delete(group_id, clean)
    return f"已拒绝入群验证：{clean}（未踢出）"


def scan_users(
    store: VerifyStore, event: object, group_id: str
) -> tuple[str, list[str]]:
    """列出本群 pending。返回 (摘要, 要 @ 的 QQ)。非管理员列表为空。"""
    # 扫描也属于管理能力
    if not is_admin(event):
        return REJECT_MESSAGE, []
    ids = store.list_user_ids(group_id)
    # 没有待验证的人就不用 @
    if not ids:
        return "本群没有待验证的人。", []
    lines = [f"本群待验证 {len(ids)} 人，请尽快在群里发送包含验证码的消息："]
    lines.extend(ids)
    return "\n".join(lines), ids
