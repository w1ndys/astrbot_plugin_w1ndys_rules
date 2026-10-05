# 业务层：WebUI 名单里的群拦截 QQ 群名片卡片。
# 单独线路，不看触发词，不送模型。命中后走和违禁词一样的撤回、禁言、飞书。

import json

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS,
    FORBIDDEN_REASON_GROUP_CARD,
    GROUP_CARD_HIT,
)
from .feature_enable import feature_on
from .forbidden_action import apply_hit_actions
from .qq_role import is_qq_group_staff
from .whitelist import should_skip_forbidden, speaker_id

async def handle_group_card(
    config: object,
    event: object,
    group_id: str,
    poster=None,
    log_store=None,
    whitelist=None,
    blacklist=None,
    mute_store=None,
) -> tuple[bool, str]:
    """处理一条群名片。handled=True 时入口要停 LLM。

    当前群不在名单里、不是群名片、群主或管理员，都不处置。
    """
    # 这个群没写进 WebUI 名单，后面的命令和违禁词继续
    if not feature_on(config, FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS, group_id):
        return False, ""

    # 不是群名片就不要拦
    if not is_group_card(event):
        return False, ""
    # 群主管理员发测试卡片不处置，避免自己被禁言
    if is_qq_group_staff(event):
        _log.info("[rules] group_card skip group=%s reason=staff", group_id)
        return False, ""

    # 这一群或全局加了白且没被拉黑，群名片不处置
    if should_skip_forbidden(whitelist, blacklist, group_id, speaker_id(event)):
        _log.info("[rules] group_card skip group=%s reason=whitelist", group_id)
        return False, ""
    _log.info("[rules] group_card hit group=%s", group_id)
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        GROUP_CARD_HIT,
        GROUP_CARD_HIT,
        poster,
        log_store,
        FORBIDDEN_REASON_GROUP_CARD,
        mute_store=mute_store,
    )
    return True, remind


def is_group_card(event: object) -> bool:
    """消息链里有没有 QQ 群名片卡片。只认真实群名片结构，不把所有 Json 当群名片。"""
    getter = getattr(event, "get_messages", None)
    # 残缺事件没有消息链
    if not callable(getter):
        return False
    for comp in getter() or []:
        # 只看 Json 段，文本和图片不是卡片
        if type(comp).__name__ != "Json":
            continue
        card = _unwrap_card(getattr(comp, "data", None))
        # 解出群名片特征就拦
        if _looks_like_group_card(card):
            return True
    return False



def _looks_like_group_card(card: dict) -> bool:
    """按真实群名片 payload 认：prompt 前缀、qun.share、或 contact.tag。"""
    # 解不开就不是
    if not card:
        return False
    prompt = card.get("prompt")
    # QQ 预览就是「群名片: 群名」
    if isinstance(prompt, str) and prompt.startswith("群名片"):
        return True
    # 这条真实卡片的业务来源是群分享
    if card.get("bizsrc") == "qun.share":
        return True
    meta = card.get("meta")
    # 没有 meta.contact 就不是这张群名片
    if not isinstance(meta, dict):
        return False
    contact = meta.get("contact")
    # contact 不是对象就不是群名片
    if not isinstance(contact, dict):
        return False
    # 卡片角标写着群名片才认
    return contact.get("tag") == "群名片"


def _unwrap_card(data: object) -> dict:
    """把字符串或嵌套 data 解成卡片对象。解不开返回空字典。"""
    current = data
    # 协议端有时整段是 JSON 字符串
    if isinstance(current, str):
        current = _parse_json_object(current)
    # 不是对象就不是卡片
    if not isinstance(current, dict):
        return {}
    nested = current.get("data")
    # aiocqhttp 的 Json 组件 data 里还套一层字符串
    if isinstance(nested, str):
        parsed = _parse_json_object(nested)
        # 套一层之后才是 prompt/meta
        if parsed:
            return parsed
    return current


def _parse_json_object(text: str) -> dict:
    """把字符串解析成对象。失败或不是对象就空字典。"""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    # 数组或数字不是卡片
    if not isinstance(value, dict):
        return {}
    return value
