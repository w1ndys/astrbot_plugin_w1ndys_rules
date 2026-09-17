# 业务层：违禁词大模型判断的提示词和「是/否」解析。
# 不调用 AstrBot，不处置。真正补全由入口层去做。

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import (
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_KIND_SAMPLE,
    FORBIDDEN_KIND_TRIGGER,
)
from .forbidden_match import find_trigger


class ForbiddenTestPlan:
    """WebUI 测试的下一步。status 是 error / skip / ready。"""

    def __init__(
        self,
        status: str,
        message: str,
        trigger: str = "",
        system: str = "",
        user: str = "",
    ) -> None:
        self.status = status
        self.message = message
        self.trigger = trigger
        self.system = system
        self.user = user


def config_text(config: object, key: str) -> str:
    """从插件配置里取字符串。没有配置或不是字符串时给空串。"""
    # 没挂上 WebUI 配置就当全空，测试会提示先填
    if config is None:
        return ""
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当没有
    if not callable(getter):
        return ""
    value = getter(key)
    # None 和空值都当没填
    if value is None:
        return ""
    return str(value)


def parse_yes_no(raw: str) -> str:
    """只认去掉首尾空白后整句是「是」或「否」。其它输出算失败。"""
    text = raw.strip()
    # 必须整句相等，带解释或标点都不算，避免误处置
    if text == "是":
        return "yes"
    if text == "否":
        return "no"
    return "fail"


def build_system_prompt(samples: str, guideline: str) -> str:
    """拼给模型看的系统提示。要求只回答是或否。"""
    return (
        "你是群规违禁判断器。只根据下面的设定和样本判断用户消息是否违禁。\n"
        "只回答「是」或「否」其中一个，不要解释，不要标点，不要换行。\n"
        "设定：\n"
        f"{guideline.strip()}\n"
        "样本：\n"
        f"{samples.strip()}"
    )


def plan_forbidden_test(
    config: object,
    store: ForbiddenStore,
    group_id: str,
    text: str,
) -> ForbiddenTestPlan:
    """按本群数据库配置决定测试要不要送模型。不调用模型，不处置。"""
    payload = text.strip()
    # 空文本测不了
    if not payload:
        return ForbiddenTestPlan("error", "请填写要测的文本。")
    words = store.list_contents(group_id, FORBIDDEN_KIND_TRIGGER)
    # 本群数据库没有触发词就永远不会进模型。
    if not words:
        return ForbiddenTestPlan("error", "请先给本群添加违禁触发词。")
    trigger = find_trigger(payload, words)
    # 没命中触发词，按正式路径一样不送模型
    if not trigger:
        return ForbiddenTestPlan("skip", "未命中触发词，不会送模型。")
    samples = "\n".join(store.list_contents(group_id, FORBIDDEN_KIND_SAMPLE))
    guideline = config_text(config, FORBIDDEN_CFG_GUIDELINE)
    # WebUI 判断准则和本群数据库样本都为空时，模型没有判断依据。
    if not samples.strip() and not guideline.strip():
        return ForbiddenTestPlan(
            "error",
            "请先填写 WebUI 判断准则，或给本群添加违禁样本。",
            trigger,
        )
    return ForbiddenTestPlan(
        "ready",
        "",
        trigger,
        build_system_prompt(samples, guideline),
        payload,
    )


def test_result_payload(plan: ForbiddenTestPlan, verdict: str) -> dict:
    """把测试计划收成给 WebUI 的 JSON。不带飞书 webhook，也不带回完整系统提示。"""
    # 还没到模型，或配置不全
    if plan.status != "ready":
        return {
            "status": plan.status,
            "trigger": plan.trigger,
            "message": plan.message,
        }
    if verdict == "yes":
        # 模型整句只回了「是」
        message = f"命中触发词「{plan.trigger}」，模型判定：是违禁。测试路径不撤回、不禁言、不发飞书。"
    elif verdict == "no":
        # 模型整句只回了「否」
        message = f"命中触发词「{plan.trigger}」，模型判定：不是违禁。"
    else:
        message = (
            f"命中触发词「{plan.trigger}」，模型没有只回答「是」或「否」，本轮不处置。"
        )
    return {
        "status": verdict,
        "trigger": plan.trigger,
        "message": message,
    }


async def complete_yes_no(provider: object, system: str, user: str) -> str:
    """用当前提供商补全一次。没有提供商或答得不规范都算失败。"""
    chat = getattr(provider, "text_chat", None)
    # 没挂提供商就不能判断
    if not callable(chat):
        return "fail"
    try:
        resp = await chat(prompt=user, system_prompt=system)
    except Exception:  # noqa: BLE001 - 提供商异常类型不固定，失败时必须停止处置
        # 模型挂了也当判断失败，测试页会提示，不会处置
        return "fail"
    # 空响应按失败
    if resp is None:
        return "fail"
    # 提供商把错误写在 role=err 里
    if getattr(resp, "role", "") == "err":
        return "fail"
    raw = getattr(resp, "completion_text", "") or ""
    return parse_yes_no(str(raw))
