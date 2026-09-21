# 业务层：WebUI 名单里的群拦截 QQ 群名片卡片。
# 单独线路，不看触发词，不送模型。命中后走和违禁词一样的撤回、禁言、飞书。

import json

from ..entity.constants import FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS, GROUP_CARD_HIT
from .forbidden_action import apply_hit_actions
from .qq_role import is_qq_group_staff


async def handle_group_card(
    config: object,
    event: object,
    group_id: str,
    poster=None,
) -> tuple[bool, str]:
    """处理一条群名片。handled=True 时入口要停 LLM。

    当前群不在名单里、不是群名片、群主或管理员，都不处置。
    """
    # 这个群没写进 WebUI 名单，后面的命令和违禁词继续
    if not _group_listed(config, group_id):
        return False, ""
    # 不是群名片就不要拦
    if not is_group_card(event):
        return False, ""
    # 群主管理员发测试卡片不处置，避免自己被禁言
    if is_qq_group_staff(event):
        return False, ""
    remind = await apply_hit_actions(
        event, config, group_id, GROUP_CARD_HIT, GROUP_CARD_HIT, poster
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


def _group_listed(config: object, group_id: str) -> bool:
    """当前群号是否写在 WebUI 名单里。没写就不拦。"""
    # 没有群号对不上名单
    if not group_id:
        return False
    for item in _config_group_ids(config):
        # 名单里这一项就是本群
        if item == group_id:
            return True
    return False


def _config_group_ids(config: object) -> list:
    """从 WebUI 取出要拦截群名片的群号。新格式是按条添加的列表。"""
    value = _config_raw(config, FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS)
    # 新 WebUI 按条添加，得到字符串数组
    if isinstance(value, list):
        return _clean_group_ids(value)
    # 旧文本框还没重新保存时，仍按空格/逗号拆，避免名单突然失效
    if isinstance(value, str):
        return _clean_group_ids(value.replace(",", " ").split())
    return []


def _config_raw(config: object, key: str):
    """从插件配置取出原值。没有配置返回 None。"""
    # 没挂上 WebUI 配置就当全空
    if config is None:
        return None
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当没有
    if not callable(getter):
        return None
    return getter(key)


def _clean_group_ids(items: list) -> list:
    """去掉空项和首尾空白，得到可比较的群号。"""
    result = []
    for item in items:
        text = str(item).strip()
        # 空项忽略
        if not text:
            continue
        result.append(text)
    return result


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
    # 卡片角标写着群名片
    if contact.get("tag") == "群名片":
        return True
    return False


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
