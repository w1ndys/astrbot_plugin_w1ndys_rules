# 业务层：待验证失败禁言、通过解禁。调 OneBot，失败不往上抛。

import asyncio


async def mute_user(
    event: object, group_id: str, user_id: str, seconds: int
) -> None:
    """禁言指定群员。0 秒、禁自己、没有 QQ 号都跳过。"""
    # 配置成 0 表示这次不禁言
    if seconds <= 0:
        return
    await _set_ban(event, group_id, user_id, seconds)


async def unmute_user(event: object, group_id: str, user_id: str) -> None:
    """解禁指定群员。没有 QQ 号就跳过。"""
    await _set_ban(event, group_id, user_id, 0)


async def _set_ban(
    event: object, group_id: str, user_id: str, seconds: int
) -> None:
    """调 set_group_ban。自己和坏号码都不发。"""
    # 拿不到人就禁不了
    if not user_id:
        return
    # 不能禁言机器人自己
    if user_id == _self_id(event):
        return
    try:
        uid = int(user_id)
        gid = int(group_id)
    except (TypeError, ValueError):
        return
    await _call_action(
        event,
        "set_group_ban",
        group_id=gid,
        user_id=uid,
        duration=seconds,
    )


def _self_id(event: object) -> str:
    """机器人自己的 QQ。没有就空串。"""
    getter = getattr(event, "get_self_id", None)
    # 残缺事件没有这个方法
    if getter is None:
        return ""
    value = getter()
    # 空值统一成空串
    if not value:
        return ""
    return str(value)


async def _call_action(event: object, action: str, **kwargs: object) -> bool:
    """调 OneBot 一个动作。失败只返回 False，不往上抛。"""
    bot = getattr(event, "bot", None)
    # 当前事件不是 OneBot 就做不了禁言
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
    except Exception:  # noqa: BLE001 - OneBot 适配器异常类型不固定
        # 协议失败不打断后面的群文案
        return False
    return True


def message_id_from_result(result: object) -> str:
    """从发消息回报里取出 message_id。没有就空串。"""
    # send 失败或测试桩没回报
    if result is None:
        return ""
    # OneBot 常见回报是字典
    if isinstance(result, dict):
        mid = result.get("message_id")
        # 有的实现把 ID 放在 data 里
        if mid is None or mid == "":
            data = result.get("data")
            # data 不是字典就当没有
            if isinstance(data, dict):
                mid = data.get("message_id")
        # 还是没有
        if mid is None or mid == "":
            return ""
        return str(mid)
    mid = getattr(result, "message_id", None)
    # 对象上也没有这个字段
    if mid is None or mid == "":
        return ""
    return str(mid)


async def recall_message_id(event: object, message_id: str) -> None:
    """撤回指定消息。没有 ID 或不是数字就跳过。"""
    # 入群时没记下提示消息，撤不了
    if not message_id:
        return
    try:
        parsed = int(message_id)
    except (TypeError, ValueError):
        return
    await _call_action(event, "delete_msg", message_id=parsed)


async def send_group_plain(event: object, group_id: str, text: str) -> None:
    """往指定群发一句纯文本。群号坏了就跳过。"""
    # 空文案不要发空消息
    if not text:
        return
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return
    await _call_action(event, "send_group_msg", group_id=gid, message=text)


async def send_verify_prompt(event: object, user_id: str, text: str) -> str:
    """发出入群验证说明，返回消息 ID。没有 send 就空串。"""
    sender = getattr(event, "send", None)
    # 测试桩或残缺事件发不出去
    if not callable(sender):
        return ""
    from astrbot.api.message_components import At, Plain

    # 有入群 QQ 就先 @，和欢迎语一样
    if user_id:
        result = await sender(
            event.chain_result([At(qq=user_id), Plain("\n" + text)])
        )
    else:
        result = await sender(event.plain_result(text))
    return message_id_from_result(result)
