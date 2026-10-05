# 业务层：违禁命中后的处置。不走 group-agent，因为那边 guard 认的是发言人。
# 群员触发时发言人不是管理员，复用会直接被拒。本层自己调 OneBot，自己发飞书。

import asyncio
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    DEFAULT_FORBIDDEN_MUTE_SECONDS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_RECALL_HISTORY_COUNT,
    MAX_FORBIDDEN_MUTE_SECONDS,
)
from .forbidden_judge import config_text
from .forbidden_log import save_hit_log, take_payload


def mute_seconds(config: object) -> int:
    """从 WebUI 取禁言秒数。空值用默认，负数当 0，超过 QQ 上限就夹住。"""
    raw = config_text(config, FORBIDDEN_CFG_MUTE_SECONDS)
    # 没填就用 60 秒
    if not raw.strip():
        return DEFAULT_FORBIDDEN_MUTE_SECONDS
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_FORBIDDEN_MUTE_SECONDS
    # 0 表示这次不禁言
    if seconds < 0:
        return 0
    # QQ 单次最多 30 天
    if seconds > MAX_FORBIDDEN_MUTE_SECONDS:
        return MAX_FORBIDDEN_MUTE_SECONDS
    return seconds


def remind_text(config: object) -> str:
    """群里要发的提醒。留空表示不发群内提醒。"""
    return config_text(config, FORBIDDEN_CFG_REMIND_TEXT).strip()


def feishu_webhook(config: object) -> str:
    """飞书自定义机器人地址。不是 https 的直接丢掉，避免误发到别的地方。"""
    url = config_text(config, FORBIDDEN_CFG_FEISHU_WEBHOOK).strip()
    # 没填就不发
    if not url:
        return ""
    # 只接受 https，拒绝 http / 其它协议
    if not url.startswith("https://"):
        return ""
    return url


def feishu_text_payload(text: str) -> dict:
    """飞书自定义机器人的文本消息体。"""
    return {"msg_type": "text", "content": {"text": text}}


def feishu_alert_text(
    group_id: str,
    user_id: str,
    trigger: str,
    text: str,
    happened_at: str = "",
    judge_reason: str = "",
) -> str:
    """管理员在飞书里看到的内容。不含 webhook。"""
    lines = [
        "违禁词命中",
        f"群：{group_id}",
        f"成员：{user_id}",
    ]
    # 有消息时间才写，读不到就省略
    if happened_at:
        lines.append(f"时间：{happened_at}")
    lines.append(f"触发词：{trigger}")
    # 模型短原因方便人工看误判
    if judge_reason:
        lines.append(f"判定原因：{judge_reason}")
    lines.append(f"消息：{text}")
    return "\n".join(lines)


_BEIJING = ZoneInfo("Asia/Shanghai")


def message_happened_at(event: object) -> str:
    """从事件取出北京时间字符串。读不到返回空串。"""
    ts = _event_unix(event)
    # 没有时间就不写这一行
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, _BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _event_unix(event: object) -> int | None:
    """消息 unix 秒。优先 message_obj.timestamp / time，再看 raw_message。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象就没时间
    if obj is None:
        return None
    for key in ("timestamp", "time"):
        ts = _as_unix(getattr(obj, key, None))
        # 找到第一个能用的字段就停
        if ts is not None:
            return ts
    return _unix_from_raw(getattr(obj, "raw_message", None))


def _unix_from_raw(raw: object) -> int | None:
    """从 OneBot 原始 dict 取 time。"""
    # 没有原始包
    if raw is None:
        return None
    if isinstance(raw, dict):
        for key in ("time", "timestamp"):
            ts = _as_unix(raw.get(key))
            # dict 里有合法时间
            if ts is not None:
                return ts
        return None
    getter = getattr(raw, "get", None)
    # 不是 dict 也没有 get
    if not callable(getter):
        return None
    for key in ("time", "timestamp"):
        ts = _as_unix(getter(key))
        if ts is not None:
            return ts
    return None


def _as_unix(raw: object) -> int | None:
    """把数字收成秒。毫秒会除 1000。"""
    # 空值不当 0 点
    if raw is None or raw is False:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    # 13 位当毫秒
    if value > 10000000000:
        value = value // 1000
    # 非正数没有意义
    if value <= 0:
        return None
    return value


def post_json(url: str, body: dict) -> None:
    """同步 POST JSON。调用方丢到线程里，避免堵住事件循环。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def sender_id_of(event: object) -> str:
    """发言人 QQ 号。没有就禁不了。"""
    getter = getattr(event, "get_sender_id", None)
    # 取不到发送者就不要禁言
    if not callable(getter):
        return ""
    return str(getter() or "")


def self_id_of(event: object) -> str:
    """机器人自己的 QQ 号，用来拦住禁言自己。"""
    getter = getattr(event, "get_self_id", None)
    # 没有就当拿不到
    if not callable(getter):
        return ""
    return str(getter() or "")


def message_id_of(event: object) -> object:
    """协议端消息 ID。没有就撤不了。"""
    obj = getattr(event, "message_obj", None)
    # 没有消息对象时没法取 ID
    if obj is None:
        return None
    raw = getattr(obj, "message_id", None)
    # 字段缺失或空值都当没有
    if raw is None or raw == "":
        return None
    return raw


async def call_result(event: object, action: str, **kwargs: object) -> object:
    """调 OneBot 并回传结果。失败回 None。"""
    bot = getattr(event, "bot", None)
    # 当前事件不是 OneBot 就做不了撤回禁言
    if bot is None:
        return None
    api = getattr(bot, "api", None)
    # 有 bot 但没有 api 同样不能调
    if api is None:
        return None
    chat = getattr(api, "call_action", None)
    # 接口名不对就当失败
    if not callable(chat):
        return None
    try:
        return await asyncio.wait_for(chat(action, **kwargs), 15)
    except Exception:  # noqa: BLE001 - OneBot 适配器异常类型不固定，失败时继续后续提醒
        # 协议失败不打断后面的提醒和飞书
        return None


async def call_action(event: object, action: str, **kwargs: object) -> bool:
    """调 OneBot 一个动作。失败只返回 False，不往上抛。"""
    result = await call_result(event, action, **kwargs)
    # 超时或适配器抛错时 call_result 给 None
    if result is None:
        return False
    return True


async def recall_message(event: object) -> None:
    """撤回当前这条群消息。没有 ID 就跳过。"""
    mid = message_id_of(event)
    # 没有消息 ID 协议端撤不了
    if mid is None:
        return
    parsed = _int_id(mid)
    # ID 不是数字协议端不认
    if parsed is None:
        return
    await call_action(event, "delete_msg", message_id=parsed)


def history_messages(raw: object) -> list:
    """从 get_group_msg_history 回报取出消息列表。"""
    # 有的实现直接回列表
    if isinstance(raw, list):
        return raw
    getter = getattr(raw, "get", None)
    # 不是对象就没有消息
    if not callable(getter):
        return []
    msgs = getter("messages")
    # 常见是 {messages: [...]}
    if isinstance(msgs, list):
        return msgs
    data = getter("data")
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


def msg_user_id(msg: object) -> str:
    """历史消息里的发送人 QQ 号。"""
    # 不是对象就对不上人
    if not isinstance(msg, dict):
        return ""
    info = msg.get("sender")
    # 有的实现把发送人摊在外层
    if not isinstance(info, dict):
        info = {}
    return str(info.get("user_id") or msg.get("user_id") or "")


def _int_id(raw: object):
    """消息 ID 转 int。不是数字就当没有。"""
    # 空值撤不了
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def user_history_ids(raw: object, user_id: str) -> list:
    """最近一页里这个人的消息 ID，去重且保持原顺序。"""
    ids = []
    seen = set()
    for msg in history_messages(raw):
        # 不是这个违禁用户的不撤
        if msg_user_id(msg) != user_id:
            continue
        mid = _int_id(msg.get("message_id") if isinstance(msg, dict) else None)
        # 没有数字 ID 协议端撤不了
        if mid is None:
            continue
        # 同一条不要删两次
        if mid in seen:
            continue
        seen.add(mid)
        ids.append(mid)
    return ids


async def recall_user_recent(event: object, group_id: str) -> None:
    """拉群最近 30 条，撤回其中这个违禁用户的消息。当前条已撤过则跳过。"""
    user_id = sender_id_of(event)
    # 拿不到人就对不上历史
    if not user_id:
        return
    # 机器人自己的消息不要撤
    if user_id == self_id_of(event):
        return
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return
    raw = await call_result(
        event,
        "get_group_msg_history",
        group_id=gid,
        message_seq=0,
        count=FORBIDDEN_RECALL_HISTORY_COUNT,
    )
    # 协议失败当这页没有历史，当前条已经撤过
    if raw is None:
        _log.info("[rules] forbidden history skip group=%s reason=no_history", group_id)
        return
    current = _int_id(message_id_of(event))
    ids = user_history_ids(raw, user_id)
    extra = 0
    for mid in ids:
        # 当前违禁消息刚撤过，不要再删一次
        if current is not None and mid == current:
            continue
        ok = await call_action(event, "delete_msg", message_id=mid)
        # 记成功数，失败的继续下一条
        if ok:
            extra += 1
    _log.info(
        "[rules] forbidden history recall group=%s user=%s extra=%s scanned=%s",
        group_id,
        user_id,
        extra,
        len(ids),
    )


async def mute_member(event: object, group_id: str, seconds: int) -> None:
    """禁言发言人。0 秒、禁自己、没有 QQ 号都跳过。"""
    # 配置成 0 表示这次不禁言
    if seconds <= 0:
        return
    user_id = sender_id_of(event)
    # 拿不到人就禁不了
    if not user_id:
        return
    # 不能禁言机器人自己
    if user_id == self_id_of(event):
        return
    try:
        uid = int(user_id)
        gid = int(group_id)
    except (TypeError, ValueError):
        return
    await call_action(
        event,
        "set_group_ban",
        group_id=gid,
        user_id=uid,
        duration=seconds,
    )


async def notify_feishu(
    config: object,
    group_id: str,
    trigger: str,
    text: str,
    event: object,
    poster=None,
    judge_reason: str = "",
) -> None:
    """有 https webhook 才发。测试可传入 poster，避免真的打到飞书。"""
    url = feishu_webhook(config)
    # 没配或不是 https 就不发
    if not url:
        return
    body = feishu_text_payload(
        feishu_alert_text(
            group_id,
            sender_id_of(event),
            trigger,
            text,
            message_happened_at(event),
            judge_reason,
        )
    )
    send = poster or post_json
    try:
        await asyncio.to_thread(send, url, body)
    except Exception:  # noqa: BLE001 - 网络层异常类型不固定，不能中断群内处置
        # 飞书失败不影响群里的撤回和禁言
        return


async def apply_hit_actions(
    event: object,
    config: object,
    group_id: str,
    trigger: str,
    text: str,
    poster=None,
    log_store=None,
    reason_code: str = "",
    judge_reason: str = "",
    mute_store=None,
) -> str:
    """命中后：先采原文，再撤回当前条和该用户近 30 条、禁言、飞书、写日志。"""
    payload = await take_payload(log_store, reason_code, event)
    await recall_message(event)
    await recall_user_recent(event, group_id)
    seconds = mute_seconds(config)
    await mute_member(event, group_id, seconds)
    user_id = sender_id_of(event)
    # 记下这次违禁禁言，管理员解禁后才知道该给谁加白
    if mute_store is not None:
        # 秒数大于 0 才算真的禁了言
        if seconds > 0:
            await mute_store.mark(group_id, user_id)
        else:
            # 这次没禁言，上次留下的标记不能留着
            await mute_store.clear(group_id, user_id)
    await notify_feishu(
        config, group_id, trigger, text, event, poster, judge_reason
    )
    await save_hit_log(
        log_store,
        group_id,
        sender_id_of(event),
        reason_code,
        trigger,
        payload,
        judge_reason,
    )
    return remind_text(config)

