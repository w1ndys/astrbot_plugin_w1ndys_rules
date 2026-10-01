# 业务层：群里直接发的管理命令，不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
#
# 欢迎语设/查是代码路径。管理员自然语言增删改查关键词仍要唤醒，那是进 Agent 的门。
# 关键词批量已迁到 WebUI 表，这里不再认。功能开/关已迁到 WebUI 群号名单。
#
# 无权的人误发要静默：这条路径会看到所有群消息，回拒绝语会刷屏。

import logging

from ..data.welcome_store import WelcomeStore
from ..entity.constants import CMD_WELCOME_SET, CMD_WELCOME_SHOW
from .welcome_admin import can_edit_welcome, set_welcome, show_welcome

_log = logging.getLogger("astrbot_plugin_w1ndys_rules")

def _has_command_header(first: str, cmd: str) -> bool:
    """第一行是命令，或命令后面紧跟空格/Tab 再跟正文。"""
    # 第一行整句就是命令，正文在后面的换行里
    if first == cmd:
        return True
    # 命令后面必须隔开，避免连在一起的字被误认
    return (
        first.startswith(cmd)
        and len(first) > len(cmd)
        and first[len(cmd)] in (" ", "\t")
    )


def parse_admin_command(text: str) -> str:
    """看是不是欢迎语命令。返回动作名；不是命令返回空串。"""
    payload = text.replace("\ufeff", "").strip()
    # 空消息不是命令
    if not payload:
        return ""
    # 查询必须整条相等，后面再跟字就不认
    if payload == CMD_WELCOME_SHOW:
        return "welcome_show"
    first = payload.splitlines()[0].strip()
    # 「欢迎语 设置」后面才是文案
    if _has_command_header(first, CMD_WELCOME_SET):
        return "welcome_set"
    return ""


async def handle_admin_command(
    welcome: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> tuple[bool, str]:
    """处理欢迎语设/查。handled=True 时入口必须停 LLM。"""
    action = parse_admin_command(text)
    # 不是管理命令，交给后面的关键词匹配
    if not action:
        return False, ""
    # 欢迎语：无权误发静默，也不让这条再去撞关键词或进模型
    if not can_edit_welcome(event):
        _log.info("[rules] admin skip group=%s action=%s reason=no_perm", group_id, action)
        return True, ""
    _log.info("[rules] admin cmd group=%s action=%s", group_id, action)
    # 查看本群独立配置
    if action == "welcome_show":
        return True, show_welcome(welcome, event, group_id)
    return True, await set_welcome(welcome, event, group_id, text)
