# 业务层：插件 Pages 欢迎语表。不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 空串保存表示本群关闭；删除行表示改回继承全局。

from ..data.welcome_store import WelcomeStore
from ..entity.constants import WELCOME_MAX_LEN, WELCOME_PAGE_SIZE


def _page_number(value: object, default: int) -> int:
    """把请求里的页码收成正整数。坏值用默认。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    # 页码从 1 起，0 和负数当没填
    if number < 1:
        return default
    return number


def list_welcomes(store: WelcomeStore, payload: dict) -> dict:
    """按群号过滤后分页。群号空串看全部。"""
    group_id = str(payload.get("group_id") or "").strip()
    page = _page_number(payload.get("page"), 1)
    page_size = _page_number(payload.get("page_size"), WELCOME_PAGE_SIZE)
    # 每页最多 100，避免一次把整表拉到浏览器
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    items, total = store.list_page(group_id, offset, page_size)
    rows = []
    for gid, content in items:
        rows.append({"group_id": gid, "content": content})
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def save_welcome(store: WelcomeStore, payload: dict) -> tuple:
    """写入或覆盖本群欢迎语。空文案落库，表示本群关闭。"""
    group_id = str(payload.get("group_id") or "").strip()
    # 没有群号就不知道写进哪一群
    if not group_id:
        return False, "群号不能是空的。"
    content = str(payload.get("content") or "").strip()
    # 超长文案不落库，避免误贴整篇文章
    if len(content) > WELCOME_MAX_LEN:
        return False, f"欢迎语太长了，最多 {WELCOME_MAX_LEN} 个字。"
    await store.set_content(group_id, content)
    # 空串关闭本群欢迎，优先于开启名单
    if not content:
        return True, "已关闭本群欢迎语。独立配置为空，即使在开启名单里也不发。"
    return True, "已保存本群欢迎语。"


async def remove_welcome(store: WelcomeStore, payload: dict) -> tuple:
    """删掉本群独立配置，入群时改回用全局文案。"""
    group_id = str(payload.get("group_id") or "").strip()
    # 群号对不上主键，删不了
    if not group_id:
        return False, "群号不能是空的。"
    removed = await store.delete(group_id)
    # 没删掉说明本来就没这行
    if not removed:
        return False, "这一群没有独立欢迎语。"
    return True, "已删除本群独立配置，入群时改回用全局文案。"
