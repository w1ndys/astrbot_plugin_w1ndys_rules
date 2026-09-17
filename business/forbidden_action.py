# 业务层：违禁命中后的处置。不走 group-agent，因为那边 guard 认的是发言人。
# 群员触发时发言人不是管理员，复用会直接被拒。本层自己调 OneBot，自己发飞书。

import asyncio
import json
import urllib.request

from ..entity.constants import (
    DEFAULT_FORBIDDEN_MUTE_SECONDS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    MAX_FORBIDDEN_MUTE_SECONDS,
)
from .forbidden_judge import config_text


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


def feishu_alert_text(group_id: str, user_id: str, trigger: str, text: str) -> str:
    """管理员在飞书里看到的内容。不含 webhook。"""
    return (
        f"违禁词命中\n群：{group_id}\n成员：{user_id}\n触发词：{trigger}\n消息：{text}"
    )


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


async def call_action(event: object, action: str, **kwargs: object) -> bool:
    """调 OneBot 一个动作。失败只返回 False，不往上抛。"""
    bot = getattr(event, "bot", None)
    # 当前事件不是 OneBot 就做不了撤回禁言
    if bot is None:
        return False
    api = getattr(bot, "api", None)
    # 有 bot 但没有 api 同样不能调
    if api is None:
        return False
    chat = getattr(api, "call_action", None)
    # 接口名不对就当失败
    if not callable(chat):
        return False
    try:
        await asyncio.wait_for(chat(action, **kwargs), 15)
    except Exception:  # noqa: BLE001 - OneBot 适配器异常类型不固定，失败时继续后续提醒
        # 协议失败不打断后面的提醒和飞书
        return False
    return True


async def recall_message(event: object) -> None:
    """撤回当前这条群消息。没有 ID 就跳过。"""
    mid = message_id_of(event)
    # 没有消息 ID 协议端撤不了
    if mid is None:
        return
    try:
        parsed = int(mid)
    except (TypeError, ValueError):
        return
    await call_action(event, "delete_msg", message_id=parsed)


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
) -> None:
    """有 https webhook 才发。测试可传入 poster，避免真的打到飞书。"""
    url = feishu_webhook(config)
    # 没配或不是 https 就不发
    if not url:
        return
    body = feishu_text_payload(
        feishu_alert_text(group_id, sender_id_of(event), trigger, text)
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
) -> str:
    """命中后：撤回、禁言、飞书。返回群提醒文案，空串表示不在群里提醒。"""
    await recall_message(event)
    await mute_member(event, group_id, mute_seconds(config))
    await notify_feishu(config, group_id, trigger, text, event, poster)
    return remind_text(config)
