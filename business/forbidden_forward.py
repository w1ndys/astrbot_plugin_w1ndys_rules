# 业务层：从原始 payload 的 message 取出合并转发节点正文。
# 不调 get_forward_msg。节点可以再套 forward，按层递归抽字。

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

