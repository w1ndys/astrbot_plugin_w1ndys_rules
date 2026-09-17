# 业务层：群里直接发的管理命令，不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
#
# 开、关、批量、欢迎语设/查是代码路径，和群员命中关键词一类。管理员自然语言
# 增删改查仍要唤醒，那是进 Agent 的门，不在这里处理。
#
# 群员误发要静默：这条路径会看到所有群消息，回「只有管理员」会刷屏。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.keyword_store import KeywordStore
from ..data.welcome_store import WelcomeStore
from ..entity.constants import (
    CMD_FORBIDDEN_OFF,
    CMD_FORBIDDEN_ON,
    CMD_KEYWORD_BATCH,
    CMD_KEYWORD_OFF,
    CMD_KEYWORD_ON,
    CMD_WELCOME_OFF,
    CMD_WELCOME_ON,
    CMD_WELCOME_SET,
    CMD_WELCOME_SHOW,
)
from .auth import is_admin
from .keyword_batch import import_rules
from .switch_command import (
    run_forbidden_switch,
    run_keyword_switch,
    run_welcome_switch,
)
from .welcome_admin import set_welcome, show_welcome


def _has_command_header(first: str, cmd: str) -> bool:
    """第一行是命令，或命令后面紧跟空格/Tab 再跟正文。"""
    # 第一行整句就是命令，正文在后面的换行里
    if first == cmd:
        return True
    # 命令后面必须隔开，避免「关键词 批量导入」这种连在一起的字被误认
    if first.startswith(cmd) and len(first) > len(cmd) and first[len(cmd)] in " \t":
        return True
    # 对不上命令头，这条不是该命令
    return False


def parse_admin_command(text: str) -> str:
    """看是开、关、批量还是欢迎语。返回动作名；不是命令返回空串。"""
    payload = text.replace("\ufeff", "").strip()
    # 空消息不是命令
    if not payload:
        return ""
    # 开、关、查询必须整条相等，后面再跟字就不认
    if payload == CMD_KEYWORD_ON:
        return "keyword_on"
    if payload == CMD_KEYWORD_OFF:
        return "keyword_off"
    if payload == CMD_FORBIDDEN_ON:
        return "forbidden_on"
    if payload == CMD_FORBIDDEN_OFF:
        return "forbidden_off"
    if payload == CMD_WELCOME_ON:
        return "welcome_on"
    if payload == CMD_WELCOME_OFF:
        return "welcome_off"
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
    switches: GroupSwitchStore,
    welcome: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> tuple[bool, str]:
    """处理开、关、批量、欢迎语设/查。handled=True 时入口必须停 LLM。"""
    action = parse_admin_command(text)
    # 不是管理命令，交给后面的关键词匹配
    if not action:
        return False, ""
    # 群员误发静默，也不让这条再去撞关键词或进模型
    if not is_admin(event):
        return True, ""
    return True, await _run_admin_action(
        action, context, keywords, switches, welcome, event, group_id, text
    )


async def _run_admin_action(
    action: str,
    context: object,
    keywords: KeywordStore,
    switches: GroupSwitchStore,
    welcome: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> str:
    """管理员已经确认后，按动作执行并返回群里要发的文案。"""
    # 打开本群关键词回复
    if action == "keyword_on":
        return await run_keyword_switch(switches, event, group_id, True)
    # 关闭本群关键词回复
    if action == "keyword_off":
        return await run_keyword_switch(switches, event, group_id, False)
    # 打开本群违禁词
    if action == "forbidden_on":
        return await run_forbidden_switch(switches, event, group_id, True)
    # 关闭本群违禁词
    if action == "forbidden_off":
        return await run_forbidden_switch(switches, event, group_id, False)
    # 打开本群欢迎语开关，入群发送下一刀再接
    if action == "welcome_on":
        return await run_welcome_switch(switches, event, group_id, True)
    # 关闭本群欢迎语开关
    if action == "welcome_off":
        return await run_welcome_switch(switches, event, group_id, False)
    # 查看本群已保存的欢迎语
    if action == "welcome_show":
        return show_welcome(welcome, event, group_id)
    # 设置本群欢迎语文案
    if action == "welcome_set":
        return await set_welcome(welcome, event, group_id, text)
    # 剩下只可能是关键词批量，parse 不会给出别的动作名
    return await import_rules(context, keywords, event, group_id, text)
