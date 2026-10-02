# 业务层：Pages 群名映射。不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 本层不调 OneBot；协议结果由入口传入后在这里拆成群号和群名。

from ..data.group_name_store import GroupNameStore
from ..entity.group_name import GroupName


def list_group_names(store: GroupNameStore) -> dict:
    """读出已保存的映射。给三页对照群号。"""
    return {"items": _items_to_rows(store.list_all())}


def parse_group_list(raw: object) -> list:
    """从 get_group_list 回报抽出映射。失败或不认识的形状当空列表。"""
    rows = _group_list_rows(raw)
    items = []
    for row in rows:
        item = _row_to_item(row)
        # 不是一条群资料就丢掉
        if item is None:
            continue
        items.append(item)
    return items


def pull_group_names(raw: object) -> dict:
    """把协议结果收成和 list 相同的 JSON。不写库。"""
    return {"items": _items_to_rows(parse_group_list(raw))}


async def save_group_names(store: GroupNameStore, payload: dict) -> tuple:
    """把草稿 upsert 进映射表。协议没带回的旧行不删。"""
    raw_items = payload.get("items")
    # 前端必须交列表，避免把整份配置误写进来
    if not isinstance(raw_items, list):
        return False, "items 必须是列表。"
    items = []
    for row in raw_items:
        item = _row_to_item(row)
        # 空群号或不是对象不写
        if item is None:
            continue
        items.append(item)
    await store.upsert_many(items)
    return True, "已保存群名。"


def _items_to_rows(items: list) -> list:
    """实体转页面 JSON。"""
    rows = []
    for item in items:
        rows.append({"group_id": item.group_id, "group_name": item.group_name})
    return rows


def _group_list_rows(raw: object) -> list:
    """取出群资料数组。直接列表，或包在 data 里。"""
    # NapCat 有时直接回列表
    if isinstance(raw, list):
        return raw
    getter = getattr(raw, "get", None)
    # 不是对象就没有群
    if not callable(getter):
        return []
    data = getter("data")
    # 常见是 {data: [...]}
    if isinstance(data, list):
        return data
    return []


def _row_to_item(row: object):
    """一行群资料收成实体。群号空则丢掉。"""
    # 协议或草稿里混进非对象就跳过
    if not isinstance(row, dict):
        return None
    group_id = str(row.get("group_id") or "").strip()
    # 没有群号对不上功能名单
    if not group_id:
        return None
    group_name = str(row.get("group_name") or "").strip()
    return GroupName(group_id, group_name)
