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
