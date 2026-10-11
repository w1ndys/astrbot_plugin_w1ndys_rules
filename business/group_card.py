# 业务层：WebUI 名单里的群拦截联系人卡片（群名片、推荐好友）。
# 单独线路，不看触发词，不送模型。命中后走和违禁词一样的撤回、禁言、飞书。

import json

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    CARD_IDENTITY_MAX_LEN,
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

    # 取出这条消息里的联系人卡片；不是卡片就不要拦
    card = find_contact_card(event)
    if not card:
        return False, ""
    # 群主管理员发测试卡片不处置，避免自己被禁言
    if is_qq_group_staff(event):
        _log.debug("[群管] 群名片跳过 群号=%s 原因=群管", group_id)
        return False, ""

    # 这一群或全局加了白且没被拉黑，群名片不处置
    if should_skip_forbidden(whitelist, blacklist, group_id, speaker_id(event)):
        _log.debug("[群管] 群名片跳过 群号=%s 原因=白名单", group_id)
        return False, ""
    # 身份那行字既进飞书也进日志，管理员才能看出宣传的是哪个群或哪个 QQ
    identity = card_identity(card)
    _log.debug("[群管] 群名片命中 群号=%s", group_id)
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        GROUP_CARD_HIT,
        identity,
        poster,
        log_store,
        FORBIDDEN_REASON_GROUP_CARD,
        log_text=identity,
        mute_store=mute_store,
    )
    return True, remind


def find_contact_card(event: object) -> dict:
    """消息链里第一条联系人卡片。没有就返回空字典。"""
    getter = getattr(event, "get_messages", None)
    # 残缺事件没有消息链
    if not callable(getter):
        return {}
    for comp in getter() or []:
        # 只看 Json 段，文本和图片不是卡片
        if type(comp).__name__ != "Json":
            continue
        card = _unwrap_card(getattr(comp, "data", None))
        # 解出联系人卡片特征就返回它，交给调用方取身份
        if _looks_like_contact_card(card):
            return card
    return {}


def is_group_card(event: object) -> bool:
    """消息链里有没有联系人卡片。群名片和推荐好友都算，不把所有 Json 当卡片。"""
    return bool(find_contact_card(event))



def _looks_like_contact_card(card: dict) -> bool:
    """按真实卡片 payload 认联系人卡片家族：群名片和推荐好友都算。"""
    # 解不开就不是
    if not card:
        return False
    # 两者共用 app 和 view，这是联系人卡片家族的稳定特征，比 prompt 文案可靠
    if card.get("app") == "com.tencent.contact.lua" and card.get("view") == "contact":
        return True
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



def card_identity(card: dict) -> str:
    """把联系人卡片收成一行人话：群名片给群号和群名，推荐好友给账号。"""
    contact = _contact_of(card)
    # 没有 contact 就退回角标和昵称，至少留下线索
    if not contact:
        return _clip(_tag_and_name(card))
    tag = str(contact.get("tag") or "").strip()
    name = str(contact.get("nickname") or "").strip()
    # 群名片：被分享的群号藏在头像地址里，解不出就只写群名
    if tag == "群名片":
        group_no = _group_no_of(contact)
        # 有群号时写全，管理员一眼能看出宣传的是哪个群
        if group_no:
            return _clip(f"群名片：群号 {group_no} 群名 {name}")
        return _clip(f"群名片：群名 {name}")
    account = _account_of(contact)
    # 推荐好友的 contact 字段直接写着账号
    if account:
        return _clip(f"{tag or '联系人卡片'}：{account}")
    return _clip(_tag_and_name(card))


def _contact_of(card: dict) -> dict:
    """取 meta.contact 对象。没有就空字典。"""
    meta = card.get("meta")
    # 没有 meta 就不是联系人卡片结构
    if not isinstance(meta, dict):
        return {}
    contact = meta.get("contact")
    # contact 不是对象就没有可读字段
    if not isinstance(contact, dict):
        return {}
    return contact


def _group_no_of(contact: dict) -> str:
    """从头像地址的 gh/<群号> 段取群号。取不到返回空串。"""
    parts = [part for part in str(contact.get("avatar") or "").split("/") if part]
    for index, part in enumerate(parts):
        # QQ 群头像路径固定是 gh/<群号>/...，后面一段就是群号
        if part == "gh" and index + 1 < len(parts):
            return _digits_of(parts[index + 1])
    return ""


def _digits_of(text: str) -> str:
    """只留数字。结果为空说明这段不是号码。"""
    result = ""
    for char in text:
        # 非数字字符直接丢掉，避免把路径拼进群号
        if char.isdigit():
            result += char
    return result


def _account_of(contact: dict) -> str:
    """推荐好友的账号字段，去掉「账号：」前缀。没有就空串。"""
    raw = str(contact.get("contact") or "").strip()
    # 短横线表示这一项本来没有内容
    if not raw or raw == "-":
        return ""
    for label in ("账号：", "账号:"):
        # 前缀只是给人看的标签，去掉更好读
        if raw.startswith(label):
            return raw[len(label):].strip()
    return raw


def _tag_and_name(card: dict) -> str:
    """兜底身份：角标加昵称。都取不到就写联系人卡片。"""
    contact = _contact_of(card)
    parts = []
    for value in (contact.get("tag"), contact.get("nickname")):
        text = str(value or "").strip()
        # 空字段不拼进去，避免出现多余空格
        if text:
            parts.append(text)
    # 什么都取不到也要留一句话，免得日志空着
    if not parts:
        return "联系人卡片"
    return " ".join(parts)


def _clip(text: str) -> str:
    """超长截断。卡片字段是外部输入，不能让它撑爆日志和飞书。"""
    # 没超上限原样返回
    if len(text) <= CARD_IDENTITY_MAX_LEN:
        return text
    return text[:CARD_IDENTITY_MAX_LEN]
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
