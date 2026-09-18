# 业务层：待验证的人私聊交码。对了撤群里的提示、解禁、在群里报通过；错了只回私聊一句。
# 群消息不再走入群验证交码。

from ..data.verify_store import VerifyStore
from .verify_action import recall_message_id, send_group_plain, unmute_user
from .verify_check import code_in_text

# 交码成功发到群里；失败只回私聊。不提踢人。
PASS_REPLY = "已通过人机验证。"
FAIL_REPLY = "验证码不对。"


def match_private_code(
    store: VerifyStore, user_id: str, text: str
) -> tuple[str, str, str]:
    """在这个人的 pending 里按码匹配。返回 (动作, 群号, 提示消息 ID)。"""
    rows = store.list_by_user(user_id)
    # 这个人没有任何待验证，私聊当普通对话
    if not rows:
        return "", "", ""
    # 没有文本不当交码，图片语音不罚
    if not text:
        return "", "", ""
    for group_id, code, prompt_id in rows:
        # 消息里带着这串码就算通过这一群
        if code_in_text(text, code):
            return "pass", group_id, prompt_id
    return "fail", "", ""


async def handle_verify_private(
    store: VerifyStore,
    event: object,
    user_id: str,
    text: str,
) -> tuple[bool, str]:
    """处理私聊交码。返回 (已处理, 私聊文案)。已处理时入口要停 LLM。"""
    # 没有 QQ 号对不上 pending
    if not user_id:
        return False, ""
    action, group_id, prompt_id = match_private_code(store, user_id, text)
    # 不是待验证私聊，后面的流程继续
    if not action:
        return False, ""
    # 对不上任何一群的码，只在私聊说不对
    if action == "fail":
        return True, FAIL_REPLY
    await store.delete(group_id, user_id)
    await recall_message_id(event, prompt_id)
    await unmute_user(event, group_id, user_id)
    await send_group_plain(event, group_id, PASS_REPLY)
    # 成功不在私聊再回一句
    return True, ""
