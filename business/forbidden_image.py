# 业务层：图片违禁路。二维码层先跑；原图本地 OCR 有可见文字就送是/否模型。
# 不读协议 payload 的 ocr/text。不走触发词。测试页不处置。

import inspect

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_QRCODE,
    IMAGE_TRANSCRIPT_HIT,
    QRCODE_HIT,
)
from .forbidden_action import apply_hit_actions
from .forbidden_judge import (
    ForbiddenTestPlan,
    build_system_prompt,
    complete_yes_no,
    config_text,
)
from .forbidden_ocr import ocr_text_from_b64
from .forbidden_qr import qr_found_in_b64

_STICKER_TYPES = {"Face", "Mface"}

def message_has_image(event: object) -> bool:
    """消息链里有没有图片或表情段。"""
    for _comp in _image_comps(event):
        return True
    return False


def plan_image_test(
    config: object, transcript: str, qr_found: bool
) -> ForbiddenTestPlan:
    """测试页：二维码层或转写有字就送模型。不调用模型，不处置。"""
    # 解码层检出，描述里写二维码也不算
    if qr_found:
        return ForbiddenTestPlan(
            "qr", "二维码直接违禁，不送模型。", QRCODE_HIT
        )
    text = transcript.strip()
    # 空转写没有判断材料，本刀不升视觉
    if not text:
        return ForbiddenTestPlan("skip", "没有可见文字，不会送模型。")
    samples = config_text(config, FORBIDDEN_CFG_SAMPLES)
    guideline = config_text(config, FORBIDDEN_CFG_GUIDELINE)
    # 和文本路一样，没准则没样本就测不了
    if not samples.strip() and not guideline.strip():
        return ForbiddenTestPlan(
            "error", "请先填写 WebUI 判断准则或违禁样本。"
        )
    return ForbiddenTestPlan(
        "ready",
        "",
        IMAGE_TRANSCRIPT_HIT,
        build_system_prompt(samples, guideline),
        _image_user(transcript),
    )


async def handle_forbidden_images(
    event: object,
    config: object,
    group_id: str,
    get_provider,
    poster=None,
    log_store=None,
    decoder=None,
    transcribe=None,
    ocr=None,
) -> tuple[bool, str]:
    """图片路：先二维码，再转写有字就送模型。没有图返回未处置。"""
    comps = _image_comps(event)
    # 纯文本不走这里
    if not comps:
        return False, ""
    names = ",".join(type(comp).__name__ for comp in comps)
    _log.info("[rules] image start group=%s comps=%s", group_id, names)
    if await _qr_hit(comps, decoder):
        _log.info("[rules] image qr hit group=%s", group_id)
        remind = await apply_hit_actions(
            event,
            config,
            group_id,
            QRCODE_HIT,
            QRCODE_HIT,
            poster,
            log_store,
            FORBIDDEN_REASON_QRCODE,
        )
        return True, remind
    text = await _transcript_of(event, comps, transcribe, ocr)
    preview = text.replace("\n", " ")[:80]
    _log.info(
        "[rules] image ocr group=%s chars=%s preview=%s",
        group_id,
        len(text),
        preview,
    )
    plan = plan_image_test(config, text, False)
    # 空转写或没设定，不打模型
    if plan.status != "ready":
        _log.info(
            "[rules] image skip group=%s status=%s msg=%s",
            group_id,
            plan.status,
            plan.message,
        )
        return False, ""
    provider = await get_provider()
    verdict = await complete_yes_no(provider, plan.system, plan.user)
    # 只有整句「是」才处置
    if verdict != "yes":
        _log.info("[rules] image verdict group=%s verdict=%s", group_id, verdict)
        return False, ""
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        plan.trigger,
        plan.user,
        poster,
        log_store,
        FORBIDDEN_REASON_IMAGE_MODEL,
    )
    _log.info("[rules] image model hit group=%s", group_id)
    return True, remind


def _image_user(transcript: str) -> str:
    """送给模型的固定格式。能走到这里说明二维码未检出。"""
    return (
        "来源: 图片转写\n"
        "可见文字:\n"
        f"{transcript}\n"
        "二维码: 未检出"
    )


def _image_comps(event: object) -> list:
    """图片和表情段。"""
    getter = getattr(event, "get_messages", None)
    # 残缺事件没有消息链
    if not callable(getter):
        return []
    items = []
    for comp in getter() or []:
        name = type(comp).__name__
        # 只收图和表情，文本不是图片路
        if name in ("Image",) or name in _STICKER_TYPES:
            items.append(comp)
    return items


def skip_vision(comp: object) -> bool:
    """表情、贴纸、gif 不跑本地 OCR，仍要过二维码层。"""
    name = type(comp).__name__
    # 协议表情不当广告载体
    if name in _STICKER_TYPES:
        return True
    loc = str(getattr(comp, "url", None) or getattr(comp, "file", None) or "")
    # gif 当表情雨，不当广告图
    return loc.lower().endswith(".gif")



async def _qr_hit(comps: list, decoder) -> bool:
    """任一图解出二维码就命中。"""
    for comp in comps:
        raw = await _comp_b64(comp)
        # 转失败当这张未检出，看下一张
        if not raw:
            continue
        if qr_found_in_b64(raw, decoder):
            return True
    return False


async def _transcript_of(event: object, comps: list, transcribe, ocr=None) -> str:
    """原图本地 OCR。测试可注入整段转写；贴纸不跑 OCR。"""
    # 回归直接给转写，不打 RapidOCR
    if transcribe is not None:
        result = transcribe(event)
        if inspect.isawaitable(result):
            result = await result
        return str(result or "")
    parts = []
    for comp in comps:
        # 贴纸不当广告图，不跑 OCR
        if skip_vision(comp):
            _log.info(
                "[rules] image ocr skip type=%s reason=sticker_or_gif",
                type(comp).__name__,
            )
            continue
        raw = await _comp_b64(comp)
        # 下图失败当这张没字
        if not raw:
            _log.info("[rules] image ocr skip type=%s reason=no_bytes", type(comp).__name__)
            continue
        text = ocr_text_from_b64(raw, ocr)
        # 没认出字就看下一张
        if not text:
            _log.info(
                "[rules] image ocr empty type=%s b64=%s",
                type(comp).__name__,
                len(raw),
            )
            continue
        parts.append(text)
    return "\n".join(parts)


async def _comp_b64(comp: object) -> str:
    """一张图转成不带前缀的 base64。失败空串。"""
    convert = getattr(comp, "convert_to_base64", None)
    # 表情可能没有这个方法
    if not callable(convert):
        _log.info("[rules] image b64 skip type=%s reason=no_convert", type(comp).__name__)
        return ""
    try:
        raw = convert()
        if inspect.isawaitable(raw):
            raw = await raw
    except Exception:  # noqa: BLE001 - 单张失败继续其它图
        _log.info("[rules] image b64 fail type=%s", type(comp).__name__)
        return ""
    text = str(raw or "")
    if text.startswith("base64://"):
        return text[len("base64://") :]
    return text
