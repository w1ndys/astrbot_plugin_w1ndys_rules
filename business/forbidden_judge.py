# 业务层：违禁词大模型判断的提示词和「是/否」解析。
# 不调用 AstrBot，不处置。真正补全由入口层去做。

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import (
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_GLOBAL_SCOPE,
    FORBIDDEN_JUDGE_REASON_MAX,
    FORBIDDEN_KIND_TRIGGER,
)
from .forbidden_match import any_pattern_on, find_pattern_trigger, find_trigger


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
        """保存测试计划字段。"""
        self.status = status
        self.message = message
        self.trigger = trigger
        self.system = system
        self.user = user


class JudgeResult:
    """一次模型判定。verdict 是 yes / no / fail，reason 给人工看。"""

    def __init__(self, verdict: str, reason: str = "") -> None:
        """保存判定结果和可选短原因。"""
        self.verdict = verdict
        self.reason = reason


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


def parse_judge_reply(raw: str) -> JudgeResult:
    """第一行必须是「是」或「否」；其余行当短原因。"""
    text = raw.strip()
    # 空回答不能处置
    if not text:
        return JudgeResult("fail")
    lines = text.splitlines()
    verdict = parse_yes_no(lines[0].strip())
    # 第一行不规范，整段作废
    if verdict == "fail":
        return JudgeResult("fail")
    reason = "\n".join(lines[1:]).strip()
    # 过长截断，避免飞书和日志被刷
    if len(reason) > FORBIDDEN_JUDGE_REASON_MAX:
        reason = reason[:FORBIDDEN_JUDGE_REASON_MAX]
    return JudgeResult(verdict, reason)


def build_system_prompt(samples: str, guideline: str) -> str:
    """拼给模型看的系统提示。第一行是或否，违禁时第二行写短原因。"""
    return (
        "你是群规违禁判断器。只根据下面的设定和样本判断用户消息是否违禁。\n"
        "第一行只回答「是」或「否」，不要标点。\n"
        "如果第一行是「是」，第二行写不超过 40 字的违规原因，便于人工核对误判。\n"
        "如果第一行是「否」，不要写第二行。\n"
        "设定：\n"
        f"{guideline.strip()}\n"
        "样本：\n"
        f"{samples.strip()}"
    )


def plan_forbidden_test(
    config: object,
    store: ForbiddenStore,
    text: str,
) -> ForbiddenTestPlan:
    """按全局触发词和 WebUI 样本决定测试要不要送模型。不调用模型，不处置。"""
    payload = text.strip()
    # 空文本测不了
    if not payload:
        return ForbiddenTestPlan("error", "请填写要测的文本。")
    words = store.list_contents(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER)
    trigger = find_trigger(payload, words)
    # 词表没命中，再看网址/群号/QQ/手机/微信开关
    if not trigger:
        trigger = find_pattern_trigger(payload, config)
    # 词表空、规则也关，永远不会进模型
    if not trigger and not words and not any_pattern_on(config):
        return ForbiddenTestPlan("error", "请先添加违禁触发词。")
    # 没命中触发词，也没命中规则
    if not trigger:
        return ForbiddenTestPlan("skip", "未命中触发词，不会送模型。")

    samples = config_text(config, FORBIDDEN_CFG_SAMPLES)
    guideline = config_text(config, FORBIDDEN_CFG_GUIDELINE)
    # 判断准则和样本都为空时，模型没有判断依据。
    if not samples.strip() and not guideline.strip():
        return ForbiddenTestPlan(
            "error",
            "请先填写控制台判断准则或违禁样本。",
            trigger,
        )
    return ForbiddenTestPlan(
        "ready",
        "",
        trigger,
        build_system_prompt(samples, guideline),
        payload,
    )


def test_result_payload(
    plan: ForbiddenTestPlan, verdict: str, reason: str = ""
) -> dict:
    """把测试计划收成给 WebUI 的 JSON。不带飞书 webhook，也不带回完整系统提示。"""
    # 还没到模型，或配置不全
    if plan.status != "ready":
        return {
            "status": plan.status,
            "trigger": plan.trigger,
            "message": plan.message,
            "reason": "",
        }
    if verdict == "yes":
        # 模型第一行是「是」
        message = (
            f"命中触发词「{plan.trigger}」，模型判定：是违禁。"
            "测试路径不撤回、不禁言、不发飞书。"
        )
    elif verdict == "no":
        # 模型第一行是「否」
        message = f"命中触发词「{plan.trigger}」，模型判定：不是违禁。"
    else:
        message = (
            f"命中触发词「{plan.trigger}」，"
            "模型第一行没有只回答「是」或「否」，本轮不处置。"
        )
    # 有短原因就拼进说明，方便对照误判
    if reason:
        message = f"{message} 原因：{reason}"
    return {
        "status": verdict,
        "trigger": plan.trigger,
        "message": message,
        "reason": reason,
    }


async def complete_yes_no(provider: object, system: str, user: str) -> JudgeResult:
    """用当前提供商补全一次。没有提供商或答得不规范都算失败。"""
    chat = getattr(provider, "text_chat", None)
    # 没挂提供商就不能判断
    if not callable(chat):
        return JudgeResult("fail")
    try:
        resp = await chat(prompt=user, system_prompt=system)
    except Exception:  # noqa: BLE001 - 提供商异常类型不固定，失败时必须停止处置
        # 模型挂了也当判断失败，测试页会提示，不会处置
        return JudgeResult("fail")
    # 空响应按失败
    if resp is None:
        return JudgeResult("fail")
    # 提供商把错误写在 role=err 里
    if getattr(resp, "role", "") == "err":
        return JudgeResult("fail")
    raw = getattr(resp, "completion_text", "") or ""
    return parse_judge_reply(str(raw))
