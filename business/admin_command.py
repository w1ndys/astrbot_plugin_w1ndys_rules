# 业务层：群里直接发的管理命令，不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
#
# 开、关、批量是代码路径，和群员命中关键词一类。管理员自然语言增删改查仍要
# 唤醒，那是进 Agent 的门，不在这里处理。
#
# 群员误发要静默：这条路径会看到所有群消息，回「只有管理员」会刷屏。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.keyword_store import KeywordStore
from ..entity.constants import CMD_KEYWORD_BATCH, CMD_KEYWORD_OFF, CMD_KEYWORD_ON
from .auth import is_admin
from .keyword_batch import import_rules
from .switch_command import run_switch_command


def parse_admin_command(text: str) -> str:
    """看是开、关还是批量。返回动作名；不是命令返回空串。"""
    payload = text.replace("\ufeff", "").strip()
    # 空消息不是命令
    if not payload:
        return ""
    # 开、关必须整条相等，后面再跟字就不认
    if payload == CMD_KEYWORD_ON:
        return "on"
    if payload == CMD_KEYWORD_OFF:
        return "off"
    first = payload.splitlines()[0].strip()
    # 第一行只是「关键词 批量」，后面才是要导入的行
    if first == CMD_KEYWORD_BATCH:
        return "batch"
    # 命令和第一条数据写在同一行，中间必须是空格或 Tab
    if first.startswith(CMD_KEYWORD_BATCH) and first[len(CMD_KEYWORD_BATCH)] in " \t":
        return "batch"
    return ""


async def handle_admin_command(
    context: object,
    keywords: KeywordStore,
    switches: GroupSwitchStore,
    event: object,
    group_id: str,
    text: str,
) -> tuple[bool, str]:
    """处理开、关、批量。handled=True 时入口必须停 LLM，即使 reply 为空。"""
    action = parse_admin_command(text)
    # 不是管理命令，交给后面的关键词匹配
    if not action:
        return False, ""
    # 群员误发静默，也不让这条再去撞关键词或进模型
    if not is_admin(event):
        return True, ""
    # 打开本群关键词回复
    if action == "on":
        return True, await run_switch_command(switches, event, group_id, True)
    # 关闭本群关键词回复
    if action == "off":
        return True, await run_switch_command(switches, event, group_id, False)
    return True, await import_rules(context, keywords, event, group_id, text)
