# 业务层：待验证的人在群里发言，对了删 pending，错了给出文案和禁言秒数。
# 不调 OneBot，不记 last_speak。入口按返回值去禁言或解禁。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.verify_store import VerifyStore
from ..entity.constants import FEATURE_VERIFY
from .verify_check import code_in_text, mute_seconds

# 交码成功、失败时发到群里的短句。不提踢人。
PASS_REPLY = "已通过人机验证。"
FAIL_REPLY = "验证码不对，请在群里发送包含验证码的消息。"


async def handle_pending_speak(
    store: VerifyStore,
    switches: GroupSwitchStore,
    config: object,
    group_id: str,
    user_id: str,
    text: str,
) -> tuple[str, str, int]:
    """处理一条待验证发言。

    返回 (动作, 群文案, 禁言秒数)。动作是 pass / fail / 空串。
    空串表示不是待验证发言，入口继续走后面的违禁和关键词。
    """
    # 关掉之后不再拦发言，剩下的 pending 留给下次打开或管理员通过
    if not switches.is_on(group_id, FEATURE_VERIFY):
        return "", "", 0
    # 没有 QQ 号对不上 pending
    if not user_id:
        return "", "", 0
    # 没有文本不当验证发言，图片语音不罚
    if not text:
        return "", "", 0
    code = store.get_code(group_id, user_id)
    # 不是待验证的人，交给后面的流程
    if not code:
        return "", "", 0
    # 消息里带着这串码就算通过
    if code_in_text(text, code):
        await store.delete(group_id, user_id)
        return "pass", PASS_REPLY, 0
    # 待验证但没带上码，告诉他不对，入口再按秒数禁言
    return "fail", FAIL_REPLY, mute_seconds(config)
