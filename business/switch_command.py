# 业务层：群功能开、关命令。
# 只有 AstrBot 管理员能改本群开关，群员不能自己把机器人点开。

from .._shared.group_switch_store import GroupSwitchStore
from ..entity.constants import (
    CMD_FORBIDDEN_OFF,
    CMD_FORBIDDEN_ON,
    CMD_KEYWORD_OFF,
    CMD_KEYWORD_ON,
    CMD_WELCOME_OFF,
    CMD_WELCOME_ON,
    FEATURE_FORBIDDEN,
    FEATURE_KEYWORD,
    FEATURE_WELCOME,
)
from .auth import is_admin


async def run_switch_command(
    switches: GroupSwitchStore,
    event: object,
    group_id: str,
    enabled: bool,
    feature: str,
    on_cmd: str,
    off_cmd: str,
    label: str,
) -> str:
    """执行一次开关命令，返回发到群里的文本。"""
    # 只有 AstrBot 管理员能改本群开关，其余人一律拒绝
    if not is_admin(event):
        return f"只有机器人的管理员能改本群的{label}开关"
    await switches.set_on(group_id, feature, enabled)
    # 反向指令也不带前缀，和管理员日常用法一致
    if enabled:
        return f"已开启本群的{label}。要关掉可以发「{off_cmd}」。"
    return f"已关闭本群的{label}。要再打开可以发「{on_cmd}」。"


async def run_keyword_switch(
    switches: GroupSwitchStore, event: object, group_id: str, enabled: bool
) -> str:
    """开或关本群的关键词回复。"""
    return await run_switch_command(
        switches,
        event,
        group_id,
        enabled,
        FEATURE_KEYWORD,
        CMD_KEYWORD_ON,
        CMD_KEYWORD_OFF,
        "关键词回复",
    )


async def run_forbidden_switch(
    switches: GroupSwitchStore, event: object, group_id: str, enabled: bool
) -> str:
    """开或关本群的违禁词。"""
    return await run_switch_command(
        switches,
        event,
        group_id,
        enabled,
        FEATURE_FORBIDDEN,
        CMD_FORBIDDEN_ON,
        CMD_FORBIDDEN_OFF,
        "违禁词",
    )


async def run_welcome_switch(
    switches: GroupSwitchStore, event: object, group_id: str, enabled: bool
) -> str:
    """开或关本群的欢迎语。本刀只改开关，入群发送下一刀再接。"""
    return await run_switch_command(
        switches,
        event,
        group_id,
        enabled,
        FEATURE_WELCOME,
        CMD_WELCOME_ON,
        CMD_WELCOME_OFF,
        "欢迎语",
    )
