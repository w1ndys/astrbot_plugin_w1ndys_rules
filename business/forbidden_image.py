# 业务层：图片违禁路。二维码层先跑；未检出再转写、规则门、是/否模型。
# 不走近 7 天活跃豁免。测试页不处置。

import inspect

from ..entity.constants import (
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_QRCODE,
    QRCODE_HIT,
)
from .forbidden_action import apply_hit_actions
from .forbidden_image_rule import image_rule_hit
from .forbidden_judge import (
    ForbiddenTestPlan,
    build_system_prompt,
    complete_yes_no,
    config_text,
)
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
    """测试页：二维码层或转写规则门。不调用模型，不处置。"""
    # 解码层检出，描述里写二维码也不算
    if qr_found:
        return ForbiddenTestPlan(
            "qr", "二维码直接违禁，不送模型。", QRCODE_HIT
        )
    hit = image_rule_hit(transcript)
    # 规则没开就不打模型
    if not hit:
        return ForbiddenTestPlan("skip", "图片规则未命中，不会送模型。")
    samples = config_text(config, FORBIDDEN_CFG_SAMPLES)
    guideline = config_text(config, FORBIDDEN_CFG_GUIDELINE)
    # 和文本路一样，没准则没样本就测不了
    if not samples.strip() and not guideline.strip():
        return ForbiddenTestPlan(
            "error", "请先填写 WebUI 判断准则或违禁样本。", hit
        )
    return ForbiddenTestPlan(
        "ready",
        "",
        hit,
        _image_system(samples, guideline),
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
) -> tuple[bool, str]:
    """图片路：先二维码，再转写规则门。没有图返回未处置。"""
    comps = _image_comps(event)
    # 纯文本不走这里
    if not comps:
        return False, ""
    if await _qr_hit(comps, decoder):
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
    text = await _transcript_of(event, comps, transcribe)
    hit = image_rule_hit(text)
    # 没硬信号就不打模型
    if not hit:
        return False, ""
    provider = await get_provider()
    verdict = await complete_yes_no(
        provider,
        _image_system(
            config_text(config, FORBIDDEN_CFG_SAMPLES),
            config_text(config, FORBIDDEN_CFG_GUIDELINE),
        ),
        _image_user(text),
    )
    # 只有整句「是」才处置
    if verdict != "yes":
        return False, ""
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        hit,
        _image_user(text),
        poster,
        log_store,
        FORBIDDEN_REASON_IMAGE_MODEL,
    )
    return True, remind


def _image_system(samples: str, guideline: str) -> str:
    """图片路系统提示：同一套准则，补截图和网址。"""
    extra = (
        "聊天截图、海报里的招嫖、引流、联系方式和网址，"
        "与正文违禁同一标准。只根据可见文字判断。"
    )
    return build_system_prompt(samples, guideline.strip() + "\n" + extra)


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
    """表情、贴纸、gif 不打视觉转写，仍要过二维码层。"""
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


async def _transcript_of(event: object, comps: list, transcribe) -> str:
    """转写可见文字。测试可注入；贴纸不向视觉要描述。"""
    # 测试页和回归直接给转写
    if transcribe is not None:
        result = transcribe(event)
        if inspect.isawaitable(result):
            result = await result
        return str(result or "")
    parts = []
    for comp in comps:
        # 贴纸不打视觉模型
        if skip_vision(comp):
            continue
        ocr = getattr(comp, "ocr", None) or getattr(comp, "text", None)
        # 协议端自带 OCR 就用
        if ocr:
            parts.append(str(ocr))
    return "\n".join(parts)


async def _comp_b64(comp: object) -> str:
    """一张图转成不带前缀的 base64。失败空串。"""
    convert = getattr(comp, "convert_to_base64", None)
    # 表情可能没有这个方法
    if not callable(convert):
        return ""
    try:
        raw = convert()
        if inspect.isawaitable(raw):
            raw = await raw
    except Exception:  # noqa: BLE001 - 单张失败继续其它图
        return ""
    text = str(raw or "")
    if text.startswith("base64://"):
        return text[len("base64://") :]
    return text
