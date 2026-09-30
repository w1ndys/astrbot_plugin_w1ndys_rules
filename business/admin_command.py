# 业务层：群里直接发的管理命令，不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
#
# 关键词批量、欢迎语设/查是代码路径，和群员命中关键词一类。管理员自然语言
# 增删改查仍要唤醒，那是进 Agent 的门，不在这里处理。
# 功能开/关已迁到 WebUI 群号名单，这里不再认「开」「关」。
#
# 无权的人误发要静默：这条路径会看到所有群消息，回拒绝语会刷屏。
# 关键词批量只认 AstrBot 管理员；欢迎语还认本群群主和管理员。

from ..data.keyword_store import KeywordStore
from ..data.welcome_store import WelcomeStore
from ..entity.constants import (
    CMD_KEYWORD_BATCH,
    CMD_WELCOME_SET,
    CMD_WELCOME_SHOW,
)
from .auth import is_admin
from .keyword_batch import import_rules
from .welcome_admin import can_edit_welcome, set_welcome, show_welcome


def _has_command_header(first: str, cmd: str) -> bool:
    """第一行是命令，或命令后面紧跟空格/Tab 再跟正文。"""
    # 第一行整句就是命令，正文在后面的换行里
    if first == cmd:
        return True
    # 命令后面必须隔开，避免「关键词 批量导入」这种连在一起的字被误认
    return (
        first.startswith(cmd)
        and len(first) > len(cmd)
        and first[len(cmd)] in (" ", "\t")
    )


def parse_admin_command(text: str) -> str:
    """看是批量还是欢迎语。返回动作名；不是命令返回空串。"""
    payload = text.replace("\ufeff", "").strip()
    # 空消息不是命令
    if not payload:
        return ""
    # 查询必须整条相等，后面再跟字就不认
    if payload == CMD_WELCOME_SHOW:
        return "welcome_show"
    first = payload.splitlines()[0].strip()
    # 「关键词 批量」后面才是要导入的行
    if _has_command_header(first, CMD_KEYWORD_BATCH):
        return "batch"
    # 「欢迎语 设置」后面才是文案
    if _has_command_header(first, CMD_WELCOME_SET):
        return "welcome_set"
    return ""


async def handle_admin_command(
    context: object,
    keywords: KeywordStore,
    welcome: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> tuple[bool, str]:
    """处理批量、欢迎语设/查。handled=True 时入口必须停 LLM。"""
    action = parse_admin_command(text)
    # 不是管理命令，交给后面的关键词匹配
    if not action:
        return False, ""
    # 关键词批量只认 AstrBot 管理员；群员误发静默
    if action == "batch":
        # 不是 AstrBot 管理员不能批量改关键词
        if not is_admin(event):
            return True, ""
        return True, await import_rules(context, keywords, event, group_id, text)
    # 欢迎语：无权误发静默，也不让这条再去撞关键词或进模型
    if not can_edit_welcome(event):
        return True, ""
    return True, await _run_welcome_action(action, welcome, event, group_id, text)


async def _run_welcome_action(
    action: str,
    welcome: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> str:
    """权限已确认后，查看或设置本群欢迎语。"""
    # 查看本群独立配置
    if action == "welcome_show":
        return show_welcome(welcome, event, group_id)
    return await set_welcome(welcome, event, group_id, text)
