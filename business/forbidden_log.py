# 业务层：违禁日志的原因文案、原文采集和落库。
# 只给 apply_hit_actions 调用。测试页不走这里。

import inspect
import json

from ..data.forbidden_log_store import ForbiddenLogStore
from ..entity.constants import (
    FORBIDDEN_REASON_GROUP_CARD,
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_MODEL,
    FORBIDDEN_REASON_QRCODE,
)

_BASE64_PREFIX = "base64://"


def reason_text(reason_code: str, trigger: str, judge_reason: str = "") -> str:
    """把原因码收成人话。模型命中带上触发词和短原因。"""
    base = _reason_base(reason_code, trigger)
    # 没有模型短原因就用人话本身
    if not judge_reason:
        return base
    return f"{base}：{judge_reason}"


def _reason_base(reason_code: str, trigger: str) -> str:
    """不含模型短原因的人话。"""
    # 文本模型判定「是」
    if reason_code == FORBIDDEN_REASON_MODEL:
        # 有触发词写进说明，方便对照飞书短通知
        if trigger:
            return f"文本模型命中：{trigger}"
        return "文本模型命中"
    # 群名片线路，不经模型
    if reason_code == FORBIDDEN_REASON_GROUP_CARD:
        return "群名片拦截"
    # 本地解出二维码，不经模型
    if reason_code == FORBIDDEN_REASON_QRCODE:
        return "二维码直接违禁"
    # 图片转写后模型判定「是」
    if reason_code == FORBIDDEN_REASON_IMAGE_MODEL:
        # 转写命中也带触发词
        if trigger:
            return f"图片转写命中：{trigger}"
        return "图片转写命中，模型判定是"
    # 未知码仍尽量留下触发名，避免日志空白
    if trigger:
        return trigger
    return reason_code


async def take_payload(
    log_store: object, reason_code: str, event: object
) -> tuple[str, str, str] | None:
    """有仓库且有原因码才采集原文。失败返回空三列，仍要落一条。"""
    # 测试或没接线时不采集，后面也不写库
    if log_store is None:
        return None
    # 没有原因码就不知道这条日志算哪一类
    if not reason_code:
        return None
    try:
        return await collect_payload(event)
    except Exception:  # noqa: BLE001 - 采集失败不能挡住撤回禁言
        # 原文拿不到也要留下空记录，证明这次处置发生过
        return "", "[]", "[]"


async def save_hit_log(
    log_store: object,
    group_id: str,
    user_id: str,
    reason_code: str,
    trigger: str,
    payload: tuple[str, str, str] | None,
    judge_reason: str = "",
    sender_name: str = "",
) -> None:
    """把采集好的原文写入日志。失败吞掉，不影响已经做完的撤回禁言。sender_name 是命中当时的群昵称，读不到传空串。"""
    # 没采集就表示这次不记
    if payload is None:
        return
    # 仓库被拿掉时不要写
    if log_store is None:
        return
    # 类型不对就当没接上
    if not isinstance(log_store, ForbiddenLogStore):
        return
    text, json_text, images = payload
    try:
        await log_store.insert(
            group_id,
            user_id,
            reason_code,
            reason_text(reason_code, trigger, judge_reason),
            text,
            json_text,
            images,
            sender_name,
        )
    except Exception:  # noqa: BLE001 - 写库失败不能回滚撤回禁言
        # 处置已经发生，缺这条日志以后再补
        return


async def collect_payload(event: object) -> tuple[str, str, str]:
    """从事件取原文三列。text 只用 message_str，不用模型描述。"""
    text = str(getattr(event, "message_str", None) or "")
    json_text = collect_json(event)
    images = await collect_images(event)
    return text, json_text, images


def collect_json(event: object) -> str:
    """消息链里每个 Json 段的 data 原样放进数组再序列化。"""
    items = []
    for comp in _message_parts(event):
        # 只收 Json 段，文本和图片不进这一列
        if type(comp).__name__ != "Json":
            continue
        items.append(getattr(comp, "data", None))
    return json.dumps(items, ensure_ascii=False, default=str)


async def collect_images(event: object) -> str:
    """每个 Image 立刻转 base64。失败只记 ok=false，不写说明。"""
    items = []
    for comp in _message_parts(event):
        # 只收 Image 段
        if type(comp).__name__ != "Image":
            continue
        items.append(await _one_image(comp))
    return json.dumps(items, ensure_ascii=False)


def _message_parts(event: object) -> list:
    """取出消息链。没有就空列表。"""
    getter = getattr(event, "get_messages", None)
    # 残缺事件没有消息链
    if not callable(getter):
        return []
    return list(getter() or [])


async def _one_image(comp: object) -> dict:
    """转一张图。成功只留 data，失败不含说明文字。"""
    convert = getattr(comp, "convert_to_base64", None)
    # 组件没有这个方法就当没存下
    if not callable(convert):
        return {"ok": False}
    try:
        raw = convert()
        # AstrBot 有的版本这里是协程
        if inspect.isawaitable(raw):
            raw = await raw
    except Exception:  # noqa: BLE001 - 单张图失败不影响其它图和处置
        return {"ok": False}
    data = _strip_base64_prefix(raw)
    # 转出来是空串也当失败，页面只显示未能保存
    if not data:
        return {"ok": False}
    return {"ok": True, "data": data}


def _strip_base64_prefix(raw: object) -> str:
    """去掉 AstrBot 的 base64:// 前缀。其它形式原样留下。"""
    text = str(raw or "")
    # 只要约定的这一种前缀
    if text.startswith(_BASE64_PREFIX):
        return text[len(_BASE64_PREFIX) :]
    return text
