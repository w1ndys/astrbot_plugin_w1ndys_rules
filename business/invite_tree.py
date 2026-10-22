# 业务层：WebUI 邀请树页。按 QQ 跨群找树、从根展开、全部记录分页。
# 不判断 QQ 权限，Pages 只给 AstrBot 管理员开。
# 树只读，不写库；节点上限和分页上限都在常量里，避免大群一次画满。

from ..data.invite_store import InviteStore
from ..entity.constants import INVITE_PAGE_SIZE, INVITE_TREE_NODE_LIMIT
from .invite_query import clean_user_id


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


def search_trees(store: InviteStore, user_id: object) -> tuple[bool, object]:
    """跨群找这个 QQ 所在的树。号码不合法返回 False 和原因。"""
    clean, error = clean_user_id(str(user_id or ""))
    # 号码不合法时不去查库
    if error:
        return False, error
    groups = store.list_groups_of_user(clean)
    trees = []
    for group_id in groups:
        trees.append(_group_tree(store, group_id, clean))
    return True, {"user_id": clean, "groups": trees}


def _group_tree(store: InviteStore, group_id: str, user_id: str) -> dict:
    """在一个群里从根展开整棵树，标出要查的本人。"""
    edges = store.list_edges(group_id)
    by_user = {edge.user_id: edge for edge in edges}
    children = _children_map(edges)
    root_id = _find_root(by_user, user_id)
    root, truncated = _build_nodes(by_user, children, root_id, user_id)
    return {
        "group_id": group_id,
        "root_id": root_id,
        "nodes": [root],
        "truncated": truncated,
    }


def _children_map(edges: list) -> dict:
    """邀请人 -> 直接下线列表，同层按号码排序。"""
    result = {}
    for edge in edges:
        result.setdefault(edge.inviter_id, []).append(edge.user_id)
    for ids in result.values():
        ids.sort()
    return result


def _find_root(by_user: dict, user_id: str) -> str:
    """从本人往上追到没有邀请边的人。成环时停在重复节点。"""
    current = user_id
    seen = {user_id}
    while True:
        edge = by_user.get(current)
        # 没有自己的邀请边，这个人就是树的根
        if edge is None:
            return current
        nxt = edge.inviter_id
        # 缺邀请人或已经出现过，按环截断
        if not nxt or nxt in seen:
            return current
        seen.add(nxt)
        current = nxt


def _build_nodes(
    by_user: dict, children: dict, root_id: str, target_id: str
) -> tuple[dict, bool]:
    """从根按层建嵌套节点，最多 INVITE_TREE_NODE_LIMIT 个。"""
    root = _node(root_id, by_user.get(root_id), target_id)
    queue = [(root_id, root)]
    seen = {root_id}
    count = 1
    truncated = False
    while queue:
        uid, node = queue.pop(0)
        for child_id in children.get(uid, []):
            # 成环或重复出现的人不再挂第二个父节点
            if child_id in seen:
                continue
            # 到上限后只记截断，不再建节点
            if count >= INVITE_TREE_NODE_LIMIT:
                truncated = True
                continue
            seen.add(child_id)
            child = _node(child_id, by_user.get(child_id), target_id)
            node["children"].append(child)
            queue.append((child_id, child))
            count += 1
    return root, truncated


def _node(user_id: str, edge: object, target_id: str) -> dict:
    """拼一个树节点。没有自己的邀请边时邀请人和入群信息留空。"""
    return {
        "user_id": user_id,
        "inviter_id": edge.inviter_id if edge else "",
        "sub_type": edge.sub_type if edge else "",
        "created_at": edge.created_at if edge else "",
        "is_target": user_id == target_id,
        "children": [],
    }


def list_edges_page(store: InviteStore, payload: dict) -> dict:
    """全部邀请记录分页，可按群号和 QQ 过滤。"""
    group_id = str(payload.get("group_id") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    page = _page_number(payload.get("page"), 1)
    page_size = _page_number(payload.get("page_size"), INVITE_PAGE_SIZE)
    # 每页最多 100，避免一次把整表拉到浏览器
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size
    items, total = store.list_page(group_id, user_id, offset, page_size)
    return {
        "items": [_list_row(edge) for edge in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _list_row(edge: object) -> dict:
    """全部记录表的一行。字段名和前端 types 对齐。"""
    return {
        "group_id": edge.group_id,
        "user_id": edge.user_id,
        "inviter_id": edge.inviter_id,
        "sub_type": edge.sub_type,
        "created_at": edge.created_at,
    }
