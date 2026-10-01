# 业务层：从原始 payload 的 message 取出本层转发记录正文。
# 本层只含一层；嵌套转发按 id 递归 get_forward_msg。

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from .forbidden_action import call_result

_PLACEHOLDERS = (
    "[转发消息]",
    "[Forward Message]",
    "[合并转发]",
    "[Forward]",
)
_MAX_DEPTH = 8
_FORWARD_TYPES = ("forward", "forward_msg", "nodes")
_TEXT_TYPES = ("text", "plain")


def message_audit_text(event: object, message_str: str) -> str:
    """外层正文加上合并转发里的字。占位符不当正文。"""
    outer = (message_str or "").strip()
    inner = collect_forward_text(event)
    # 没有内层就仍用 AstrBot 解析出来的字
    if not inner:
        return message_str or ""
    # 外层只是转发占位符，用节点正文去审
    if not outer or outer in _PLACEHOLDERS:
        return inner
    return outer + "\n" + inner


def collect_forward_text(event: object) -> str:
    """从 raw_message.message 递归抽出转发里的可见文字。"""
    parts = []
    for item in _message_list(_raw_message(event)):
        # 不是对象就不是转发段
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").lower()
        # 只从合并转发段往下钻，普通文本段不算内层
        if kind in _FORWARD_TYPES:
            text = _walk(_forward_nodes(item), 1)
        elif _is_node(item):
            text = _walk(_node_body(item), 1)
        else:
            continue
        # 这层没字就跳过
        if text:
            parts.append(text)
    return "\n".join(parts)


def _is_node(item: dict) -> bool:
    """没有 type 的完整事件，或标准 node 段。"""
    kind = str(item.get("type") or "").lower()
    # 标准 node
    if kind == "node":
        return True
    # 普通消息段不是节点
    if kind:
        return False
    return item.get("message") is not None or item.get("content") is not None



def _raw_message(event: object) -> object:
    """取出 OneBot 原始体。"""
    obj = getattr(event, "message_obj", None)
    # 残缺事件没有消息对象
    if obj is None:
        return None
    return getattr(obj, "raw_message", None)


def _message_list(raw: object) -> list:
    """原始体上的 message 数组。"""
    getter = getattr(raw, "get", None)
    # Event 和 dict 都有 get
    if callable(getter):
        segs = getter("message")
    else:
        segs = getattr(raw, "message", None) if raw is not None else None
    # 必须是列表才往下走
    if isinstance(segs, list):
        return segs
    return []


def _walk(obj: object, depth: int) -> str:
    """列表、forward 段、节点事件都往里走，直到文本段。"""
    # 套太深就停，避免环
    if depth > _MAX_DEPTH:
        return ""
    # 一层里多段/多节点，分行拼
    if isinstance(obj, list):
        return _walk_list(obj, depth)
    # 不是对象就没有字
    if not isinstance(obj, dict):
        return ""
    kind = str(obj.get("type") or "").lower()
    # 普通文字段
    if kind in _TEXT_TYPES:
        return _text_of(obj)
    # 合并转发段：data.content 还是节点列表
    if kind in _FORWARD_TYPES:
        return _walk(_forward_nodes(obj), depth + 1)
    # 节点/完整消息事件：继续看它的 message
    inner = _node_body(obj)
    # 没有内层数组就没有字
    if inner is None:
        return ""
    return _walk(inner, depth + 1)


def _walk_list(items: list, depth: int) -> str:
    """递归每一项，空的丢掉。"""
    parts = []
    for item in items:
        text = _walk(item, depth)
        # 没抽出字就跳过
        if text:
            parts.append(text)
    return "\n".join(parts)


def _text_of(seg: dict) -> str:
    """文本段的字。"""
    data = seg.get("data")
    # 没有 data 就看段上的 text
    if not isinstance(data, dict):
        data = {}
    text = data.get("text") or seg.get("text") or ""
    return str(text).strip()


def _forward_nodes(seg: dict) -> object:
    """forward.data.content，没有就 data.message。"""
    data = seg.get("data")
    # 残缺 forward 没有节点
    if not isinstance(data, dict):
        return []
    nodes = data.get("content")
    # NapCat 把完整节点放 content
    if nodes is not None:
        return nodes
    return data.get("message") or []


def _node_body(node: dict) -> object:
    """节点正文：message、content，或 type=node 的 data.content。"""
    body = node.get("message")
    # 你贴的 payload 节点自带 message 数组
    if body is not None:
        return body
    body = node.get("content")
    # 有的实现把段列表叫 content
    if body is not None:
        return body
    data = node.get("data")
    # 标准 node 段
    if not isinstance(data, dict):
        return None
    body = data.get("content")
    # type=node 时正文在 data.content
    if body is not None:
        return body
    return data.get("message")



async def resolve_audit_text(event: object, message_str: str) -> str:
    """本层 message 抽字，嵌套转发再按 id 拉。"""
    outer = (message_str or "").strip()
    inner = collect_forward_text(event)
    fetched = await fetch_forward_text(event)
    # 嵌套层拉到的字拼在本层后面
    if fetched:
        inner = (inner + "\n" + fetched).strip() if inner else fetched
    # 内层仍空：占位符也原样交出去，后面当没命中
    if not inner:
        # 只是转发占位却抽不出字，方便对照漏检
        if outer in _PLACEHOLDERS:
            _log.info("[rules] forward empty placeholder=%s", outer)
        return message_str or ""
    # 外层只是转发占位符，用节点正文去审
    if not outer or outer in _PLACEHOLDERS:
        _log.info("[rules] forward inner_len=%s", len(inner))
        return inner
    return outer + "\n" + inner

async def fetch_forward_text(event: object) -> str:
    """本层 message 里没展开的嵌套 forward id，用 get_forward_msg 拉。"""
    ids = collect_forward_ids(event)
    # 没有待拉的 id
    if not ids:
        return ""
    return await _fetch_by_ids(event, ids)


def collect_forward_ids(event: object) -> list:
    """从本层 message 整棵树收集还没带节点的 forward id。"""
    ids = []
    seen = set()
    for fid in _ids_in(_message_list(_raw_message(event)), 1):
        # 空或重复丢掉
        if not fid or fid in seen:
            continue
        seen.add(fid)
        ids.append(fid)
    # payload.message 不是列表时，退回消息链上的 Forward id
    if not ids:
        _ids_from_chain(event, ids, seen)
    return ids


def _ids_from_chain(event: object, ids: list, seen: set) -> None:
    """AstrBot 消息链里的 Forward 组件也带 id。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就没有链
    if obj is None:
        return
    chain = getattr(obj, "message", None)
    # 链必须是列表
    if not isinstance(chain, list):
        return
    for comp in chain:
        name = type(comp).__name__.lower()
        # 只认 Forward 组件
        if name != "forward":
            continue
        fid = str(getattr(comp, "id", "") or "").strip()
        # 空 id 或重复丢掉
        if not fid or fid in seen:
            continue
        seen.add(fid)
        ids.append(fid)


def _id_of_forward(seg: dict) -> str:
    """forward 段上的资源 id。"""
    data = seg.get("data")
    # 没有 data 就看段自己
    if not isinstance(data, dict):
        data = {}
    fid = data.get("id") or seg.get("id") or ""
    return str(fid).strip()


async def _fetch_by_ids(event: object, ids: list) -> str:
    """按队列拉转发，嵌套 id 继续入队。"""
    seen = set()
    parts = []
    pending = list(ids)
    hops = 0
    while pending:
        # 套太深就停
        if hops >= _MAX_DEPTH:
            break
        fid = str(pending.pop(0) or "").strip()
        # 空或已经拉过
        if not fid or fid in seen:
            continue
        seen.add(fid)
        hops += 1
        nodes = _nodes_from_result(await _get_forward(event, fid))
        text = _walk(nodes, 1)
        # 这包有字就留下
        if text:
            parts.append(text)
        for nid in _ids_in(nodes, 1):
            # 还没拉过的嵌套 id 入队
            if nid not in seen:
                pending.append(nid)
    return "\n".join(parts)


async def _get_forward(event: object, fid: str) -> object:
    """NapCat 用 id，有的实现用 message_id。"""
    raw = await call_result(event, "get_forward_msg", id=fid)
    # 第一种参数已经拿到节点
    if _nodes_from_result(raw):
        return raw
    return await call_result(event, "get_forward_msg", message_id=fid)


def _nodes_from_result(raw: object) -> list:
    """get_forward_msg 回报里的节点列表。"""
    # 直接回列表
    if isinstance(raw, list):
        return raw
    getter = getattr(raw, "get", None)
    # 不是对象就没有节点
    if not callable(getter):
        return []
    for key in ("messages", "message", "content"):
        val = getter(key)
        # 常见是 {messages: [...]}
        if isinstance(val, list):
            return val
    data = getter("data")
    # 包了一层 data
    if isinstance(data, (dict, list)):
        return _nodes_from_result(data)
    return []


def _ids_in(obj: object, depth: int) -> list:
    """从已拉到的节点里再找出嵌套 forward id。"""
    # 套太深就停
    if depth > _MAX_DEPTH:
        return []
    if isinstance(obj, list):
        return _ids_in_list(obj, depth)
    # 不是对象就没有 id
    if not isinstance(obj, dict):
        return []
    kind = str(obj.get("type") or "").lower()
    # 合并转发段上的 id
    if kind in _FORWARD_TYPES:
        return _ids_in_forward(obj, depth)
    body = _node_body(obj)
    # 节点正文继续找
    if body is None:
        return []
    return _ids_in(body, depth + 1)


def _ids_in_list(items: list, depth: int) -> list:
    """列表里每一项的嵌套 id。"""
    ids = []
    for item in items:
        ids.extend(_ids_in(item, depth))
    return ids


def _ids_in_forward(seg: dict, depth: int) -> list:
    """没带节点的 forward 才把 id 入队，避免有正文还再拉一遍。"""
    ids = []
    nodes = _forward_nodes(seg)
    has_nodes = isinstance(nodes, list) and len(nodes) > 0
    fid = _id_of_forward(seg)
    # 已经带节点就不必按这个 id 再拉
    if fid and not has_nodes:
        ids.append(fid)
    ids.extend(_ids_in(nodes, depth + 1))
    return ids
