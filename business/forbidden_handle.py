# 业务层：群消息要不要走违禁判断、命中后怎么处置。
# 文本路要触发词。测试页不走这里。

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import CFG_FORBIDDEN_GROUPS, FORBIDDEN_REASON_MODEL
from .feature_enable import feature_on
from .forbidden_action import apply_hit_actions
from .forbidden_image import handle_forbidden_images, message_has_image
from .forbidden_judge import complete_yes_no, plan_forbidden_test
from .forbidden_video import handle_forbidden_videos
from .qq_role import is_qq_group_staff, speaker_qq_role
from .whitelist import should_skip_forbidden, speaker_id


async def handle_forbidden_message(
    config: object,
    store: ForbiddenStore,
    event: object,
    group_id: str,
    text: str,
    get_provider,
    poster=None,
    log_store=None,
    decoder=None,
    transcribe=None,
    ocr=None,
    whitelist=None,
    blacklist=None,
    mute_store=None,
) -> tuple[bool, str]:
    """处理一条群消息的违禁判断。handled=True 时入口要停 LLM。

    返回 (是否已处置, 群提醒文案)。没打开、群管、没命中、模型说否或失败，都不处置。
    """
    # 本群没写进 WebUI 违禁名单，后面的关键词回复还要继续
    if not feature_on(config, CFG_FORBIDDEN_GROUPS, group_id):
        # 纯图也要留下跳过原因，否则看起来像漏检
        if message_has_image(event):
            _log.debug("[群管] 违禁跳过 群号=%s 原因=没开启", group_id)
        return False, ""
    # QQ 群主或管理员默认安全，不送模型也不处置
    if is_qq_group_staff(event):
        _log.debug(
            "[群管] 违禁跳过 群号=%s 原因=群管 角色=%s",
            group_id,
            speaker_qq_role(event),
        )
        return False, ""

    # 这一群或全局加了白且没被拉黑，文本、OCR、二维码和群名片都不送模型
    if should_skip_forbidden(whitelist, blacklist, group_id, speaker_id(event)):
        _log.debug("[群管] 违禁跳过 群号=%s 原因=白名单", group_id)
        return False, ""
    handled, remind = await handle_forbidden_images(
        event,
        config,
        group_id,
        get_provider,
        poster,
        log_store,
        decoder,
        transcribe,
        ocr,
        store,
        mute_store=mute_store,
    )
    # 二维码或图片模型已经处置，文本路不再跑
    if handled:
        _log.debug("[群管] 违禁图片已处置 群号=%s", group_id)
        return True, remind
    handled, remind = await handle_forbidden_videos(
        event,
        config,
        group_id,
        get_provider,
        poster,
        log_store,
        decoder,
        ocr,
        store,
        mute_store=mute_store,
    )
    # 短视频二维码或视频模型已经处置，文本路不再跑
    if handled:
        _log.debug("[群管] 违禁视频已处置 群号=%s", group_id)
        return True, remind
    return await _handle_forbidden_text(
        config,
        store,
        event,
        group_id,
        text,
        get_provider,
        poster,
        log_store,
        mute_store=mute_store,
    )


async def _handle_forbidden_text(
    config: object,
    store: ForbiddenStore,
    event: object,
    group_id: str,
    text: str,
    get_provider,
    poster,
    log_store,
    mute_store=None,
) -> tuple[bool, str]:
    """文本路：触发词、整句是。"""
    plan = plan_forbidden_test(config, store, text)
    # 空文本、没触发词、没设定，都按正式路径一样不送模型
    if plan.status != "ready":
        # 空聊天不刷日志；有字或有图才记下跳过原因
        if text.strip() or message_has_image(event):
            _log.debug(
                "[群管] 违禁文本跳过 群号=%s 状态=%s 触发词=%s",
                group_id,
                plan.status,
                plan.trigger,
            )
        return False, ""
    provider = await get_provider()
    judged = await complete_yes_no(provider, plan.system, plan.user)
    # 只有第一行「是」才处置，否和乱答都不动
    if judged.verdict != "yes":
        _log.debug(
            "[群管] 违禁文本判定 群号=%s 触发词=%s 判定=%s",
            group_id,
            plan.trigger,
            judged.verdict,
        )
        return False, ""
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        plan.trigger,
        plan.user,
        poster,
        log_store,
        FORBIDDEN_REASON_MODEL,
        judged.reason,
        mute_store=mute_store,
        # 日志文本存这份送审用户文本，和飞书「消息」正文是同一份
        log_text=plan.user,
    )
    _log.debug("[群管] 违禁文本已处置 群号=%s 触发词=%s", group_id, plan.trigger)
    return True, remind
