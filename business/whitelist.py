# 业务层：违禁日志页的四个名单按钮，以及热路径的跳过判断。
#
# 本群行只影响这一群，全局行的 group_id 固定是 "global"。四个按钮只读写名单表，
# 不判断 QQ 权限，不调 OneBot，也不踢人。任一范围的黑名单压过任一范围的白名单。

from ..entity.constants import BLACKLIST_GLOBAL_SCOPE

# 号码不合法时的统一文案。日志页和后端都按这个字面量报错。
PAIR_ERROR = "群号必须是数字或 global，成员 QQ 必须是数字。"
# 加白之后这个人仍在黑名单时的后缀。白名单不会让他跳过违禁检测。
STILL_BLOCKED = "此人仍在黑名单，不会跳过违禁。"
# 两张名单在文案里的名字，拼在「本群」「全局」后面。
WHITELIST_NAME = "白名单。"
BLACKLIST_NAME = "黑名单。"


def _clean_pair(payload: dict) -> tuple[str, str, str]:
    """取出写入范围和成员 QQ。返回 (群号, QQ, 错误文案)。"""
    group_id = str(payload.get("group_id") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    # 成员 QQ 只认纯数字，昵称写进库以后查不出来
    if not user_id.isdigit():
        return "", "", PAIR_ERROR
    # 范围要么是真实群号，要么正好是 global，别的写法都拒绝
    if group_id.isdigit() or group_id == BLACKLIST_GLOBAL_SCOPE:
        return group_id, user_id, ""
    return "", "", PAIR_ERROR


def speaker_id(event: object) -> str:
    """发言人 QQ 号。没有就空串。"""
    getter = getattr(event, "get_sender_id", None)
    # 残缺事件没有这个方法
    if getter is None:
        return ""
    value = getter()
    # 空值统一成空串，省得调用方再判一次 None
    if not value:
        return ""
    return str(value)


def _scope_name(group_id: str) -> str:
    """回报文案里区分本群和全局。"""
    # 全局名单的 group_id 是固定键，不是真实群号
    if group_id == BLACKLIST_GLOBAL_SCOPE:
        return "全局"
    return "本群"


def _source_group_id(payload: dict) -> str:
    """日志行上的那一群。页面每次请求都要带，只看状态，不作为写入范围。"""
    return str(payload.get("source_group_id") or "").strip()


def _is_in(store, group_id: str, user_id: str) -> bool:
    """查一个范围。存储为 None 时当不在名单里。"""
    # 没挂存储就没有这一行
    if store is None:
        return False
    return store.is_in(group_id, user_id)


def _flags(whitelist, blacklist, group_id: str, user_id: str) -> tuple:
    """四个按钮状态，顺序固定：本群白、全局白、本群黑、全局黑。"""
    return (
        _is_in(whitelist, group_id, user_id),
        _is_in(whitelist, BLACKLIST_GLOBAL_SCOPE, user_id),
        _is_in(blacklist, group_id, user_id),
        _is_in(blacklist, BLACKLIST_GLOBAL_SCOPE, user_id),
    )

def roster_flags(whitelist, blacklist, group_id: str, user_id: str) -> dict:
    """四个名单状态的字段名。列表、详情和按钮回报共用，名字必须一致。"""
    flags = _flags(whitelist, blacklist, group_id, user_id)
    return {
        "whitelisted": flags[0],
        "global_whitelisted": flags[1],
        "group_blacklisted": flags[2],
        "global_blacklisted": flags[3],
    }


def should_skip_forbidden(whitelist, blacklist, group_id: str, user_id: str) -> bool:
    """热路径要不要跳过违禁判断。已加白且没被拉黑才跳过。"""
    # 没有群号或 QQ 对不上名单
    if not group_id or not user_id:
        return False
    # 任一范围的黑名单压过白名单，命中就照常检测
    if blacklist is not None and blacklist.is_blocked(group_id, user_id):
        return False
    # 只有这一群或全局加了白，才跳过文本、OCR、二维码和群名片
    if whitelist is not None and whitelist.is_listed(group_id, user_id):
        return True
    return False


def _join_message(list_name: str, group_id: str, added: bool) -> str:
    """加入名单的文案。本来就在要说「已在」，不能报成刚加入。"""
    tail = _scope_name(group_id) + list_name
    # 本来就在这张名单里，没写新行
    if not added:
        return "已在" + tail
    return "已加入" + tail


def _remove_message(list_name: str, group_id: str, removed: bool) -> str:
    """移出名单的文案。本来不在就说这个人不在。"""
    tail = _scope_name(group_id) + list_name
    # 本来就不在这张名单里，没删到行
    if not removed:
        return "这个人不在" + tail
    return "已移出" + tail


def _roster_reply(
    whitelist, blacklist, payload: dict, user_id: str, message: str
) -> tuple:
    """成功回报：文案加四个按钮状态。状态按日志行那一群算。"""
    result = roster_flags(whitelist, blacklist, _source_group_id(payload), user_id)
    # 文案和四个状态放在同一层，页面直接读 message
    result["message"] = message
    return True, result


def _still_blocked(blacklist, payload: dict, group_id: str, user_id: str) -> bool:
    """加白之后这个人是否仍被拉黑。写全局时用日志行的群号看本群。"""
    # 没挂黑名单就查不了
    if blacklist is None:
        return False
    # 写的是全局白名单，仍然要看他在日志行那一群有没有被拉黑
    if group_id == BLACKLIST_GLOBAL_SCOPE:
        group_id = _source_group_id(payload)
    # 没有群号对不上名单
    if not group_id:
        return False
    return blacklist.is_blocked(group_id, user_id)


async def add_whitelist(whitelist, blacklist, payload: dict) -> tuple:
    """加入白名单：先清同一范围的黑名单，再写白名单。"""
    group_id, user_id, error = _clean_pair(payload)
    # 号码不合法时不碰库
    if error:
        return False, error
    # 同一范围互斥，先清掉黑名单里这一行
    if blacklist is not None:
        await blacklist.remove(group_id, user_id)
    added = False
    # 没挂白名单存储时只做互斥清理
    if whitelist is not None:
        added = await whitelist.add(group_id, user_id)
    message = _join_message(WHITELIST_NAME, group_id, added)
    # 另一个范围还有黑名单时，这句必须补上，否则看起来像已经放行
    if _still_blocked(blacklist, payload, group_id, user_id):
        message = message + STILL_BLOCKED
    return _roster_reply(whitelist, blacklist, payload, user_id, message)


async def remove_whitelist(whitelist, blacklist, payload: dict) -> tuple:
    """移出白名单：只删 payload 指定的这一个范围。"""
    group_id, user_id, error = _clean_pair(payload)
    # 号码不合法时不碰库
    if error:
        return False, error
    removed = False
    # 没挂白名单存储就没有东西可删
    if whitelist is not None:
        removed = await whitelist.remove(group_id, user_id)
    message = _remove_message(WHITELIST_NAME, group_id, removed)
    # 本来就不在这一张名单里，如实回报失败
    if not removed:
        return False, message
    return _roster_reply(whitelist, blacklist, payload, user_id, message)


async def add_blacklist(whitelist, blacklist, payload: dict) -> tuple:
    """加入黑名单：先清同一范围的白名单，再写黑名单。拉黑不踢人。"""
    group_id, user_id, error = _clean_pair(payload)
    # 号码不合法时不碰库
    if error:
        return False, error
    # 同一范围互斥，先清掉白名单里这一行
    if whitelist is not None:
        await whitelist.remove(group_id, user_id)
    added = False
    # 没挂黑名单存储时只做互斥清理
    if blacklist is not None:
        added = await blacklist.add(group_id, user_id)
    message = _join_message(BLACKLIST_NAME, group_id, added)
    return _roster_reply(whitelist, blacklist, payload, user_id, message)


async def remove_blacklist(whitelist, blacklist, payload: dict) -> tuple:
    """移出黑名单：只删 payload 指定的这一个范围。"""
    group_id, user_id, error = _clean_pair(payload)
    # 号码不合法时不碰库
    if error:
        return False, error
    removed = False
    # 没挂黑名单存储就没有东西可删
    if blacklist is not None:
        removed = await blacklist.remove(group_id, user_id)
    message = _remove_message(BLACKLIST_NAME, group_id, removed)
    # 本来就不在这一张名单里，如实回报失败
    if not removed:
        return False, message
    return _roster_reply(whitelist, blacklist, payload, user_id, message)


async def pardon_forbidden_mute(
    whitelist, blacklist, mute_store, group_id: str, user_id: str
) -> str:
    """管理员解开违禁禁言后加本群白名单。没有标记返回空串。"""
    # 没有标记说明这次解禁和违禁无关
    if mute_store is None or not mute_store.has(group_id, user_id):
        return ""
    await mute_store.clear(group_id, user_id)
    # 只动本群行，不删全局黑名单，也不写全局白名单
    if blacklist is not None:
        await blacklist.remove(group_id, user_id)
    if whitelist is not None:
        await whitelist.add(group_id, user_id)
    # 全局还有黑名单时白名单不生效，文案要说清
    if blacklist is not None and blacklist.is_blocked(group_id, user_id):
        return f"已将 {user_id} 加入本群白名单。此人仍在黑名单，不会跳过违禁。"
    return f"已将 {user_id} 加入本群白名单。"
