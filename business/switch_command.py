# 业务层：关键词 开、关键词 关 这两个群开关命令。
# 只有 AstrBot 管理员能改本群开关，群员不能自己把机器人点开。

from .._shared.group_switch_store import GroupSwitchStore
from ..entity.constants import FEATURE_KEYWORD
from .auth import is_admin
from .wake_prefix import format_command


async def run_switch_command(
    switches: GroupSwitchStore,
    context: object,
    event: object,
    group_id: str,
    enabled: bool,
) -> str:
    """执行一次开关命令，返回发到群里的文本。"""
    # 只有 AstrBot 管理员能改本群开关，其余人一律拒绝
    if not is_admin(event):
        return "只有 AstrBot 管理员能改本群的关键词回复开关。"
    await switches.set_on(group_id, FEATURE_KEYWORD, enabled)
    # 文案里带上反向指令的实际写法，管理员不用自己去猜本机的唤醒前缀
    if enabled:
        return f"已开启本群的关键词回复。要关掉可以发「{format_command(context, '关键词 关')}」。"
    return f"已关闭本群的关键词回复。要再打开可以发「{format_command(context, '关键词 开')}」。"
