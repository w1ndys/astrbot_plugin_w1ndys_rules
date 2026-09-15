# 业务层：群员发了一条消息，要不要用关键词回复、回什么。
# 不碰数据库（只问内存快照），不碰 AstrBot（只返回文本）。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.keyword_store import KeywordStore
from ..entity.constants import FEATURE_KEYWORD


def pick_reply(
    keywords: KeywordStore,
    switches: GroupSwitchStore,
    group_id: str,
    text: str,
) -> str:
    """群员消息只走这一条。返回要发出去的文本，空串表示不回复。"""
    # 本群没开关键词回复就闭嘴。新群默认是关的，避免机器人一进群就开始刷屏
    if not switches.is_on(group_id, FEATURE_KEYWORD):
        return ""
    # 整条消息完全等于关键词才算命中，与旧机器人的行为保持一致
    return keywords.find_reply(group_id, text)
