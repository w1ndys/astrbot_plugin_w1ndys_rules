# 业务层：WebUI 关键词表。不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 校验复用 Agent 那套，录入方式改走页面，命中规则不变。

from ..data.keyword_store import KeywordStore
from ..entity.constants import KEYWORD_MAX_LEN, KEYWORD_PAGE_SIZE
from .keyword_admin import check_keyword, check_reply


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


def list_keywords(store: KeywordStore, payload: dict) -> dict:
    """按群号过滤后分页。群号空串看全部。"""
    group_id = str(payload.get("group_id") or "").strip()
    page = _page_number(payload.get("page"), 1)
    page_size = _page_number(payload.get("page_size"), KEYWORD_PAGE_SIZE)
    # 每页最多 100，避免一次把整表拉到浏览器
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    items, total = store.list_page(group_id, offset, page_size)
    rows = []
    for rule in items:
        rows.append(
            {
                "group_id": rule.group_id,
                "keyword": rule.keyword,
                "reply": rule.reply,
            }
        )
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def save_keyword(
    context: object, store: KeywordStore, payload: dict
) -> tuple[bool, str]:
    """写入或覆盖一条。校验失败返回 False 和原因。"""
    group_id = str(payload.get("group_id") or "").strip()
    # 没有群号就不知道这条规则在哪个群生效
    if not group_id:
        return False, "群号不能是空的。"
    keyword, error = check_keyword(context, str(payload.get("keyword") or ""))
    # 关键词不合法就不写库
    if error:
        return False, error
    reply, error = check_reply(str(payload.get("reply") or ""))
    # 回复不合法就不写库
    if error:
        return False, error
    await store.upsert(group_id, keyword, reply)
    return True, f"已保存「{keyword}」。"


async def remove_keyword(store: KeywordStore, payload: dict) -> tuple[bool, str]:
    """删一条。没这条也回报清楚。"""
    group_id = str(payload.get("group_id") or "").strip()
    keyword = str(payload.get("keyword") or "").strip()
    # 群号和关键词对不上主键，删不了
    if not group_id:
        return False, "群号不能是空的。"
    if not keyword:
        return False, "关键词不能是空的。"
    if len(keyword) > KEYWORD_MAX_LEN:
        return False, f"关键词太长了，最多 {KEYWORD_MAX_LEN} 个字。"
    removed = await store.delete(group_id, keyword)
    # 没删掉说明本来就没这条
    if not removed:
        return False, f"没有关键词「{keyword}」。"
    return True, f"已删除「{keyword}」。"
