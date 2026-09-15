# 业务层：/kr 开、/kr 关 这两个群开关命令。
# 只有 AstrBot 管理员能改本群开关，群员不能自己把机器人点开。

from .._shared.group_switch_store import GroupSwitchStore
from ..entity.constants import FEATURE_KEYWORD


def is_admin(event: object) -> bool:
    """当前发言人是不是 AstrBot 后台里配置的管理员。"""
    checker = getattr(event, "is_admin", None)
    # 没有这个方法就当不是管理员，宁可拒绝也不要误放行
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception:
        return False


async def run_switch_command(
    switches: GroupSwitchStore,
    event: object,
    group_id: str,
    enabled: bool,
) -> str:
    """执行一次开关命令，返回发到群里的文本。"""
    # 只有 AstrBot 管理员能改本群开关，其余人一律拒绝
    if not is_admin(event):
        return "只有 AstrBot 管理员能改本群的关键词回复开关。"
    await switches.set_on(group_id, FEATURE_KEYWORD, enabled)
    # 按本次是开还是关回不同的文案
    if enabled:
        return "已开启本群的关键词回复。"
    return "已关闭本群的关键词回复。"
