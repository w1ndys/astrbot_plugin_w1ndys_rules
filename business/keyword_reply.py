# 业务层：群员发了一条消息，要不要用关键词回复、回什么。
# 不碰数据库（只问内存快照），不碰 AstrBot（只返回文本）。

from ..data.keyword_store import KeywordStore
from ..entity.constants import CFG_KEYWORD_GROUPS
from .feature_enable import feature_on


def pick_reply(
    keywords: KeywordStore,
    config: object,
    group_id: str,
    text: str,
) -> str:
    """群员消息只走这一条。返回要发出去的文本，空串表示不回复。"""
    # 本群没写进 WebUI 名单就闭嘴。空名单即关，避免机器人一进群就开始刷屏
    if not feature_on(config, CFG_KEYWORD_GROUPS, group_id):
        return ""
    # 整条消息完全等于关键词才算命中，与旧机器人的行为保持一致
    return keywords.find_reply(group_id, text)
