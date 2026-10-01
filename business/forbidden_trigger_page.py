# 业务层：WebUI 全局违禁触发词表。不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 校验复用群里那套 clean_content，作用域仍是全局。

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import (
    FORBIDDEN_GLOBAL_SCOPE,
    FORBIDDEN_KIND_TRIGGER,
    FORBIDDEN_TRIGGER_PAGE_SIZE,
)
from .forbidden_admin import clean_content


def list_triggers(store: ForbiddenStore, payload: dict) -> dict:
    """分页列出全局触发词。q 做包含过滤。"""
    query = str(payload.get("q") or "").strip()
    page = _page_number(payload.get("page"), 1)
    page_size = _page_number(payload.get("page_size"), FORBIDDEN_TRIGGER_PAGE_SIZE)
    # 每页最多 100，避免一次把整表拉到浏览器
    page_size = min(page_size, 100)
    words = store.list_contents(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER)
    # 有搜索词就只留包含它的
    if query:
        words = [word for word in words if query in word]
    total = len(words)
    offset = (page - 1) * page_size
    rows = []
    for word in words[offset : offset + page_size]:
        rows.append({"content": word})
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def save_trigger(store: ForbiddenStore, payload: dict) -> tuple:
    """新增或修改一条。带 old_content 就是改，否则新增。"""
    content, error = clean_content(str(payload.get("content") or ""))
    # 新内容不合法整份不写
    if error:
        return False, error
    old_raw = str(payload.get("old_content") or "").strip()
    # 没填旧词按新增
    if not old_raw:
        return await _add_trigger(store, content)
    old_content, error = clean_content(old_raw)
    # 旧词不合法就不能当主键
    if error:
        return False, error
    return await _update_trigger(store, old_content, content)


async def remove_trigger(store: ForbiddenStore, payload: dict) -> tuple:
    """删一条全局触发词。"""
    content, error = clean_content(str(payload.get("content") or ""))
    # 空的或超长的不查库
    if error:
        return False, error
    removed = await store.delete(
        FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, content
    )
    # 没删掉说明本来就没有
    if not removed:
        return False, f"没有违禁触发词「{content}」，没有删除。"
    return True, f"已删除违禁触发词「{content}」。"


async def _add_trigger(store: ForbiddenStore, content: str) -> tuple:
    """写入一条，重复则失败。"""
    added = await store.add(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, content)
    # 唯一键冲突不能覆盖
    if not added:
        return False, f"已经存在违禁触发词「{content}」，没有重复添加。"
    return True, f"已添加违禁触发词「{content}」。"


async def _update_trigger(store: ForbiddenStore, old: str, new: str) -> tuple:
    """改一条已有触发词。"""
    # 内容没变不写库
    if old == new:
        return True, f"违禁触发词本来就是「{new}」，没有改动。"
    result = await store.update(
        FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, old, new
    )
    # 原词不存在不能降级成新增
    if result == "missing":
        return False, f"没有违禁触发词「{old}」，没有修改。"
    # 新词已在表里，两条都保留
    if result == "conflict":
        return False, f"已经存在违禁触发词「{new}」，没有修改。"
    return True, f"已将违禁触发词「{old}」修改为「{new}」。"


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
