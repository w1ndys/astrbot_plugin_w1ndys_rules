# 业务层：管理员用自然语言增删改查关键词规则。
#
# 本层只做四件事：判权限、校验内容、落库、组织发到群里的文案。
# 群号由入口层从事件里取好传进来，本层不碰 AstrBot 的平台 API。
#
# 「直接落库」是明确的产品选择：管理员说加就加，不搞二次确认。为了让人当场
# 发现模型理解错了，所有写操作的回报都带出最终写进库的关键词和回复。
#
# 添加和修改合成一次写入：模型不用先猜本群有没有这条。写进去后由代码回报
# 是「已添加」还是「已覆盖」。删除的完成状态也只认代码回报。
#
# 回报文案刻意把两个值分别用「」括起来、并写明「命中后回复」：本部署的全局
# 人格要求模型「回复不要太机械」，模型多半会把回报改写成口语。用标签把值和
# 角色绑死，即使被改写，关键词和回复也大概率不会丢、不会被调换。

from ..data.keyword_store import KeywordStore
from ..entity.constants import KEYWORD_LIST_LIMIT, KEYWORD_MAX_LEN, REPLY_MAX_LEN
from .auth import is_admin
from .wake_prefix import prefixes

# 非管理员统一回这句话，不透露本群到底配了什么。“管理”同时盖住查看和修改
REJECT_MESSAGE = "只有机器人的管理员能管理本群的关键词回复"


def check_keyword(context: object, keyword: str) -> tuple[str, str]:
    """校验关键词。返回（去掉首尾空白后的关键词，错误文案）；错误文案为空串表示合法。"""
    text = keyword.strip()
    # 空关键词匹配不到任何一条消息，先拦掉
    if not text:
        return "", "关键词不能是空的。"
    if len(text) > KEYWORD_MAX_LEN:
        return "", f"关键词太长了，最多 {KEYWORD_MAX_LEN} 个字。"
    # 以唤醒前缀开头会被 AstrBot 当成唤醒语剥掉，这条规则会永远匹配不到
    for prefix in prefixes(context):
        if text.startswith(prefix):
            return "", (
                f"关键词不能以「{prefix}」开头，"
                "它会被当成唤醒前缀剥掉，这条规则永远匹配不到。"
            )
    return text, ""


def check_reply(reply: str) -> tuple[str, str]:
    """校验回复文本。返回（去掉首尾空白后的回复，错误文案）；错误文案为空串表示合法。"""
    text = reply.strip()
    if not text:
        return "", "回复内容不能是空的。"
    if len(text) > REPLY_MAX_LEN:
        return "", f"回复内容太长了，最多 {REPLY_MAX_LEN} 个字。"
    return text, ""


async def write_rule(
    context: object,
    keywords: KeywordStore,
    event: object,
    group_id: str,
    keyword: str,
    reply: str,
) -> str:
    """写入一条规则。没有就新增，有就覆盖，由代码回报是哪种。"""
    # 非管理员不能改本群关键词，直接拒绝
    if not is_admin(event):
        return REJECT_MESSAGE
    clean_keyword, error = check_keyword(context, keyword)
    # 关键词不合法就不写库
    if error:
        return error
    clean_reply, error = check_reply(reply)
    # 回复不合法就不写库
    if error:
        return error
    # 先看原来有没有，才能如实回报是「已添加」还是「已覆盖」
    current = keywords.rule_of(group_id, clean_keyword)
    # 内容和原来一模一样就不写库
    if current is not None and current.reply == clean_reply:
        return f"关键词「{clean_keyword}」的回复本来就是「{clean_reply}」，没有改动。"
    await keywords.upsert(group_id, clean_keyword, clean_reply)
    # 原来有这条就是覆盖，没有就是新增
    action = "已覆盖" if current is not None else "已添加"
    return f"{action}关键词「{clean_keyword}」，命中后回复「{clean_reply}」。"


async def delete_rule(
    keywords: KeywordStore,
    event: object,
    group_id: str,
    keyword: str,
) -> str:
    """删掉一条规则。删除只认去掉首尾空白后的原文，不校验唤醒前缀。"""
    if not is_admin(event):
        return REJECT_MESSAGE
    text = keyword.strip()
    # 空关键词对不上任何一条规则，先拦掉
    if not text:
        return "关键词不能是空的。"
    # 超长词写不进库，删除也按同一上限拒绝，避免拿垃圾长串去查
    if len(text) > KEYWORD_MAX_LEN:
        return f"关键词太长了，最多 {KEYWORD_MAX_LEN} 个字。"
    removed = await keywords.delete(group_id, text)
    # 没删掉说明本来就没这条，别回报成删除成功
    if not removed:
        return f"本群没有关键词「{text}」，没有删除。"
    return f"已删除关键词「{text}」。"


def list_rules(keywords: KeywordStore, event: object, group_id: str) -> str:
    """列出本群现有的规则。超出上限只列前几条，并报出总数。"""
    if not is_admin(event):
        return REJECT_MESSAGE
    rules = keywords.list_rules(group_id)
    if not rules:
        return "本群还没有关键词规则。"
    lines = [f"本群共 {len(rules)} 条关键词规则："]
    for rule in rules[:KEYWORD_LIST_LIMIT]:
        lines.append(f"「{rule.keyword}」→「{rule.reply}」")
    if len(rules) > KEYWORD_LIST_LIMIT:
        rest = len(rules) - KEYWORD_LIST_LIMIT
        lines.append(f"（只列出前 {KEYWORD_LIST_LIMIT} 条，其余 {rest} 条未显示）")
    return "\n".join(lines)
