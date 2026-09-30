# 业务层：违禁日志只读页。不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 列表不回原文三列；详情按 id 取，图片只给 img 用的 src。

import json

from ..data.forbidden_log_store import ForbiddenLogStore
from ..entity.constants import FORBIDDEN_LOG_PAGE_SIZE
from ..entity.forbidden_log import ForbiddenLog


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


def list_logs(store: ForbiddenLogStore, payload: dict) -> dict:
    """按群、用户、原因过滤后分页。列表不含 text / json / images。"""
    group_id = str(payload.get("group_id") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    reason_code = str(payload.get("reason_code") or "").strip()
    page = _page_number(payload.get("page"), 1)
    page_size = _page_number(payload.get("page_size"), FORBIDDEN_LOG_PAGE_SIZE)
    # 每页最多 100，避免一次把整表拉到浏览器
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    items, total = store.list_page(
        group_id, user_id, reason_code, offset, page_size
    )
    rows = []
    for item in items:
        rows.append(_list_row(item))
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_log(store: ForbiddenLogStore, payload: dict) -> tuple[bool, object]:
    """按 id 取详情。没有这条返回 False 和原因。"""
    try:
        log_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return False, "日志编号不对。"
    # id 从 1 起
    if log_id < 1:
        return False, "日志编号不对。"
    item = store.get(log_id)
    # 这个 id 还没写过
    if item is None:
        return False, "没有这条日志。"
    return True, _detail_row(item)


def _list_row(item: ForbiddenLog) -> dict:
    """列表行。不带原文，避免把 base64 和完整 JSON 送到表格。"""
    return {
        "id": item.id,
        "group_id": item.group_id,
        "user_id": item.user_id,
        "reason_code": item.reason_code,
        "reason_text": item.reason_text,
        "created_at": item.created_at,
    }


def _detail_row(item: ForbiddenLog) -> dict:
    """详情。图片只给 src，失败不含 data。"""
    return {
        "id": item.id,
        "group_id": item.group_id,
        "user_id": item.user_id,
        "reason_code": item.reason_code,
        "reason_text": item.reason_text,
        "created_at": item.created_at,
        "text": item.text,
        "json": _parse_json_field(item.json_text),
        "pictures": _parse_pictures(item.images),
    }


def _parse_json_field(raw: str) -> object:
    """把库里的 json 列解成对象。解不开就原样字符串。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 坏数据仍给页面看原文，不当数组
        return raw


def _parse_pictures(raw: str) -> list:
    """把 images 列收成页面可用的图片项。成功只留 src。"""
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # 不是数组就没有图
    if not isinstance(items, list):
        return []
    pictures = []
    for item in items:
        pictures.append(_one_picture(item))
    return pictures


def _one_picture(item: object) -> dict:
    """一张图。失败只有 ok=false，不带回 data。"""
    # 不是对象就当没存下
    if not isinstance(item, dict):
        return {"ok": False}
    # 采集时已经记失败
    if not item.get("ok"):
        return {"ok": False}
    data = str(item.get("data") or "")
    # 空串不能当图
    if not data:
        return {"ok": False}
    return {"ok": True, "src": _data_url(data)}


def _data_url(data: str) -> str:
    """给 <img> 用的 data URL。按常见文件头猜类型。"""
    # JPEG
    if data.startswith("/9j/"):
        return "data:image/jpeg;base64," + data
    # GIF
    if data.startswith("R0lGOD"):
        return "data:image/gif;base64," + data
    # WebP
    if data.startswith("UklGR"):
        return "data:image/webp;base64," + data
    return "data:image/png;base64," + data
