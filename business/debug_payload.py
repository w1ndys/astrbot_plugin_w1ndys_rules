# 业务层：管理员 debug，查看指定消息的原始 OneBot payload。
# 引用或 message_id 看那条；否则拉群历史，可按发送人/关键词筛，一页不够再拉。

import asyncio
import json

from .auth import is_admin

REJECT_MESSAGE = "只有机器人的管理员能查看原始消息。"
NOT_FOUND = "没有取到这条消息。"
NO_MATCH = "没有找到符合条件的消息。"
# 私聊单条别太长，超了就拆开发。
_CHUNK = 3500
_PAGE = 20
_MAX_PAGES = 5


async def inspect_payload(
    event: object,
    group_id: str,
    message_id: str = "",
    sender: str = "",
    keyword: str = "",
) -> str:
    """查出指定消息的原始 payload，私聊发给管理员。"""
    # 群员不能看别人的原始消息
    if not is_admin(event):
        return REJECT_MESSAGE
    target = str(message_id or "").strip() or reply_id_of(event)
    # 填了 ID 或引用了消息，就按那条查
    if target:
        raw = await fetch_msg(event, target)
        # 协议没这条或 ID 不是数字
        if raw is None:
            return NOT_FOUND
    else:
        raw = await search_history(
            event, group_id, sender, keyword, current_id_of(event)
        )
        # 历史里对不上发送人或关键词
        if raw is None:
            return NO_MATCH
    text = dump_payload(raw)
    sent = await send_private_chunks(event, text)
    # 私聊发出去了，群里只回一句，避免模型把 JSON 贴出去
    if sent:
        return f"原始 payload 已私聊发给你，共 {len(text)} 字。不要把全文贴到群里。"
    return text


def reply_id_of(event: object) -> str:
    """从当前消息的引用段取出被引用消息 ID。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就没有引用
    if obj is None:
        return ""
    found = _id_in_chain(getattr(obj, "message", None))
    # 消息链里已经有引用
    if found:
        return found
    raw = getattr(obj, "raw_message", None)
    # 普通文本没有 raw
    if raw is None:
        return ""
    return _id_in_chain(_raw_message_list(raw))


def current_id_of(event: object) -> str:
    """当前这条管理命令自己的消息 ID。"""
    getter = getattr(event, "get_message_id", None)
    # 优先用事件方法
    if callable(getter):
        return str(getter() or "")
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就没有 ID
    if obj is None:
        return ""
    return str(getattr(obj, "message_id", "") or "")


def dump_payload(raw: object) -> str:
    """把 payload 格式化成可读 JSON。内层卡片字符串保持原样。"""
    return json.dumps(to_plain(raw), ensure_ascii=False, indent=2)


def to_plain(obj: object, depth: int = 0) -> object:
    """把 Event / dict / 列表收成能 json.dumps 的结构。"""
    # 防循环引用把栈打爆
    if depth > 8:
        return "..."
    # 基本类型原样留下
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    # 字典逐项收
    if isinstance(obj, dict):
        return {str(key): to_plain(value, depth + 1) for key, value in obj.items()}
    # 列表逐项收
    if isinstance(obj, (list, tuple)):
        return [to_plain(item, depth + 1) for item in obj]
    items = getattr(obj, "items", None)
    # aiocqhttp Event 可以当 dict 用
    if callable(items):
        try:
            return {str(key): to_plain(value, depth + 1) for key, value in items()}
        except Exception:  # noqa: BLE001 - 奇怪对象转不成 dict 就改用字符串
            return str(obj)
    return str(obj)


async def fetch_msg(event: object, message_id: str) -> object:
    """调 get_msg。ID 不是数字或失败都回 None。"""
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return None
    # 0 不是有效消息 ID
    if mid == 0:
        return None
    return await _call_result(event, "get_msg", message_id=mid)


async def search_history(
    event: object,
    group_id: str,
    sender: str,
    keyword: str,
    current_id: str,
) -> object:
    """翻群历史，筛出发送人或关键词对得上的最近一条。"""
    seq = 0
    seen: set[str] = set()
    hits: list = []
    for _ in range(_MAX_PAGES):
        page = await fetch_history_page(event, group_id, seq)
        fresh = _fresh_page(page, seen)
        # 这一页没有新消息，后面也没有了
        if not fresh:
            break
        for item in fresh:
            # 当前命令自己、对不上人、对不上词，都丢掉
            if match_message(item, sender, keyword, current_id):
                hits.append(item)
        # 已经筛到就停，刚才那条应在较新的页
        if hits:
            break
        # 不足一页说明到头了
        if len(fresh) < _PAGE:
            break
        nxt = _page_oldest_id(fresh)
        # 页游标没动就别死循环
        if not nxt or nxt == str(seq):
            break
        try:
            seq = int(nxt)
        except (TypeError, ValueError):
            break
        # 0 会重新拉最新一页
        if seq == 0:
            break
    # 多页都对不上
    if not hits:
        return None
    return pick_latest(hits)


async def fetch_history_page(event: object, group_id: str, seq: int) -> list:
    """拉一页群历史。seq=0 表示从最新开始。"""
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return []
    raw = await _call_result(
        event,
        "get_group_msg_history",
        group_id=gid,
        message_seq=seq,
        count=_PAGE,
    )
    # 协议失败
    if raw is None:
        return []
    return messages_of(raw)


def messages_of(raw: object) -> list:
    """从历史回报里取出消息列表。"""
    plain = to_plain(raw)
    # 有的实现直接回列表
    if isinstance(plain, list):
        return plain
    # 不是对象就没有消息
    if not isinstance(plain, dict):
        return []
    msgs = plain.get("messages")
    # 常见是 {messages: [...]}
    if isinstance(msgs, list):
        return msgs
    data = plain.get("data")
    # 有的包在 data 里
    if isinstance(data, list):
        return data
    # data.messages
    if isinstance(data, dict):
        inner = data.get("messages")
        # 标准 OneBot 外包一层
        if isinstance(inner, list):
            return inner
    return []


def match_message(
    msg: dict, sender: str, keyword: str, current_id: str
) -> bool:
    """当前命令自己不算；有发送人或关键词时必须对上。"""
    mid = str(msg.get("message_id") or "")
    # 不要把管理员刚发的查询当目标
    if mid and mid == str(current_id or ""):
        return False
    # 指定了谁发的
    if str(sender or "").strip() and not sender_matches(msg, sender):
        return False
    # 指定了消息里的字
    if str(keyword or "").strip() and not keyword_matches(msg, keyword):
        return False
    return True


def sender_matches(msg: dict, sender: str) -> bool:
    """QQ 号精确比；昵称和群名片包含即可。"""
    needle = str(sender or "").strip().casefold()
    # 没填发送人就不限制
    if not needle:
        return True
    info = msg.get("sender")
    # 有的实现把发送人摊在外层
    if not isinstance(info, dict):
        info = {}
    uid = str(info.get("user_id") or msg.get("user_id") or "")
    # 纯数字当 QQ 号
    if needle.isdigit() and uid == needle:
        return True
    card = str(info.get("card") or "").casefold()
    nick = str(info.get("nickname") or "").casefold()
    return needle in card or needle in nick or needle == uid


def keyword_matches(msg: dict, keyword: str) -> bool:
    """在文本段和卡片 JSON 字符串里做包含匹配。"""
    needle = str(keyword or "").strip().casefold()
    # 没填关键词就不限制
    if not needle:
        return True
    return needle in message_blob(msg).casefold()


def message_blob(msg: dict) -> str:
    """拼出可供关键词搜索的原文，包括卡片内层字符串。"""
    parts = [str(msg.get("raw_message") or ""), str(msg.get("message_str") or "")]
    segs = msg.get("message")
    # 没有消息段就只看 raw
    if not isinstance(segs, list):
        return "\n".join(parts)
    for seg in segs:
        parts.append(_seg_blob(seg))
    return "\n".join(parts)


def pick_latest(items: list) -> object:
    """多条命中时取时间最近的一条。"""
    # 调用方已经排除空列表
    if not items:
        return None
    # 有时间戳按时间
    if any(int(m.get("time") or 0) for m in items):
        return max(items, key=lambda m: int(m.get("time") or 0))
    return items[-1]


def _fresh_page(page: object, seen: set) -> list:
    """去掉已经看过的消息，收成 dict 列表。"""
    fresh = []
    # 协议失败时是空
    if not isinstance(page, list):
        return fresh
    for item in page:
        plain = to_plain(item)
        # 历史记录不是对象就跳过
        if not isinstance(plain, dict):
            continue
        mid = str(plain.get("message_id") or "")
        # 同一条不要重复筛
        if mid and mid in seen:
            continue
        if mid:
            seen.add(mid)
        fresh.append(plain)
    return fresh


def _page_oldest_id(items: list) -> str:
    """这一页里最早一条的 message_id，给下一页当游标。"""
    # 空页没有游标
    if not items:
        return ""
    # 有时间戳取最早
    if any(int(m.get("time") or 0) for m in items):
        oldest = min(items, key=lambda m: int(m.get("time") or 0))
        return str(oldest.get("message_id") or "")
    return str(items[0].get("message_id") or "")


def _seg_blob(seg: object) -> str:
    """一段消息里能搜的文字。"""
    # 组件对象少见，按字符串兜底
    if not isinstance(seg, dict):
        return str(seg)
    data = seg.get("data")
    # 没有 data 就空
    if not isinstance(data, dict):
        return str(data or "")
    text = data.get("text")
    # 普通文本段
    if text:
        return str(text)
    inner = data.get("data")
    # 卡片内层 JSON 字符串
    if inner:
        return str(inner)
    return ""


async def send_private_chunks(event: object, text: str) -> bool:
    """把全文私聊给当前管理员。失败回 False。"""
    getter = getattr(event, "get_sender_id", None)
    # 残缺事件没有发言人
    if getter is None:
        return False
    user_id = str(getter() or "")
    # 没有 QQ 号发不了私聊
    if not user_id:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    # 空内容不要发空私聊
    if not text:
        return False
    parts = [text[i : i + _CHUNK] for i in range(0, len(text), _CHUNK)]
    total = len(parts)
    for index, part in enumerate(parts, start=1):
        # 拆开的时候标序号，方便对照
        if total > 1:
            body = f"({index}/{total})\n{part}"
        else:
            body = part
        ok = await _call_action(
            event, "send_private_msg", user_id=uid, message=body
        )
        # 有一段失败就当没发成，让入口改把 JSON 回给模型
        if not ok:
            return False
    return True


def _id_in_chain(chain: object) -> str:
    """在消息段列表里找 reply 的 id。"""
    # 没有消息段
    if not isinstance(chain, (list, tuple)):
        return ""
    for item in chain:
        kind = _seg_type(item)
        # 只认引用段
        if kind != "reply":
            continue
        found = _seg_id(item)
        # 找到就用第一条引用
        if found:
            return found
    return ""


def _raw_message_list(raw: object) -> object:
    """从 OneBot Event 或 dict 取出 message 数组。"""
    getter = getattr(raw, "get", None)
    # Event 和 dict 都有 get
    if callable(getter):
        return getter("message")
    return getattr(raw, "message", None)


def _seg_type(item: object) -> str:
    """消息段类型收成小写。"""
    # OneBot 数组格式
    if isinstance(item, dict):
        inner = item.get("type")
        return str(inner or "").lower()
    value = getattr(item, "type", "")
    return str(value or "").lower()


def _seg_id(item: object) -> str:
    """引用段上的消息 ID。"""
    # OneBot 数组格式
    if isinstance(item, dict):
        data = item.get("data")
        # id 在 data 里
        if isinstance(data, dict):
            return str(data.get("id") or "")
        return str(item.get("id") or "")
    return str(getattr(item, "id", "") or "")


async def _call_result(event: object, action: str, **kwargs: object) -> object:
    """调 OneBot 并回传结果。失败回 None。"""
    chat = _chat(event)
    # 当前事件不是 OneBot
    if chat is None:
        return None
    try:
        return await asyncio.wait_for(chat(action, **kwargs), 15)
    except Exception:  # noqa: BLE001 - 适配器异常类型不固定
        return None


async def _call_action(event: object, action: str, **kwargs: object) -> bool:
    """调 OneBot。失败只回 False。"""
    result = await _call_result(event, action, **kwargs)
    # None 当失败；空 dict 也算发出去了
    return result is not None


def _chat(event: object):
    """取出 bot.api.call_action。没有就 None。"""
    bot = getattr(event, "bot", None)
    # 不是 OneBot 事件
    if bot is None:
        return None
    api = getattr(bot, "api", None)
    # 有 bot 但没有 api
    if api is None:
        return None
    chat = getattr(api, "call_action", None)
    # 接口名不对
    if not callable(chat):
        return None
    return chat
