# 业务层：群消息要不要走违禁判断、命中后怎么处置。
# 文本路要触发词。测试页不走这里。

import logging

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import CFG_FORBIDDEN_GROUPS, FORBIDDEN_REASON_MODEL
from .feature_enable import feature_on
from .forbidden_action import apply_hit_actions
from .forbidden_image import handle_forbidden_images, message_has_image
from .forbidden_judge import complete_yes_no, plan_forbidden_test
from .qq_role import is_qq_group_staff, speaker_qq_role

_log = logging.getLogger("astrbot_plugin_w1ndys_rules")


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
) -> tuple[bool, str]:
    """处理一条群消息的违禁判断。handled=True 时入口要停 LLM。

    返回 (是否已处置, 群提醒文案)。没打开、群管、没命中、模型说否或失败，都不处置。
    """
    # 本群没写进 WebUI 违禁名单，后面的关键词回复还要继续
    if not feature_on(config, CFG_FORBIDDEN_GROUPS, group_id):
        # 纯图也要留下跳过原因，否则看起来像漏检
        if message_has_image(event):
            _log.info("[rules] forbidden skip group=%s reason=not_enabled", group_id)
        return False, ""
    # QQ 群主或管理员默认安全，不送模型也不处置
    if is_qq_group_staff(event):
        _log.info(
            "[rules] forbidden skip group=%s reason=staff role=%s",
            group_id,
            speaker_qq_role(event),
        )
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
    )
    # 二维码或图片模型已经处置，文本路不再跑
    if handled:
        _log.info("[rules] forbidden image hit group=%s", group_id)
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
) -> tuple[bool, str]:
    """文本路：触发词、整句是。"""
    plan = plan_forbidden_test(config, store, text)
    # 空文本、没触发词、没设定，都按正式路径一样不送模型
    if plan.status != "ready":
        # 空聊天不刷日志；有字或有图才记下跳过原因
        if text.strip() or message_has_image(event):
            _log.info(
                "[rules] forbidden text skip group=%s status=%s trigger=%s",
                group_id,
                plan.status,
                plan.trigger,
            )
        return False, ""
    provider = await get_provider()
    verdict = await complete_yes_no(provider, plan.system, plan.user)
    # 只有整句「是」才处置，否和乱答都不动
    if verdict != "yes":
        _log.info(
            "[rules] forbidden text verdict group=%s trigger=%s verdict=%s",
            group_id,
            plan.trigger,
            verdict,
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
    )
    _log.info("[rules] forbidden text hit group=%s trigger=%s", group_id, plan.trigger)
    return True, remind
