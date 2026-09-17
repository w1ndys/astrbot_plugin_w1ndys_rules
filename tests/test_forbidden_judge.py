# 违禁词测试链路：数据库触发词门槛、数据库样本、是/否解析。不发 QQ，不处置。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_judge import (
    complete_yes_no,
    parse_yes_no,
    plan_forbidden_test,
    test_result_payload,
)
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_KIND_SAMPLE,
    FORBIDDEN_KIND_TRIGGER,
)


class FakeForbiddenStore:
    """按类型返回测试预设的数据库内容。"""

    def __init__(self, triggers=None, samples=None) -> None:
        """保存本群测试用的触发词和样本。"""
        self.triggers = triggers or []
        self.samples = samples or []

    def list_contents(self, group_id: str, kind: str) -> list[str]:
        """返回指定类型的内容，群号由调用路径负责传入。"""
        if kind == FORBIDDEN_KIND_TRIGGER:
            return self.triggers
        if kind == FORBIDDEN_KIND_SAMPLE:
            return self.samples
        return []


class FakeProvider:
    """测试用的假提供商。按预设文本回答，或按预设异常炸掉。"""

    def __init__(self, text: str = "否", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.prompts: list[tuple[str, str]] = []

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        self.prompts.append((system_prompt or "", prompt or ""))
        # 模拟提供商网络错误。
        if self.error is not None:
            raise self.error
        return FakeResponse(self.text)


class FakeResponse:
    """模拟 AstrBot 提供商的文本响应。"""

    def __init__(self, completion_text: str, role: str = "assistant") -> None:
        self.completion_text = completion_text
        self.role = role


class ForbiddenJudgeTest(unittest.TestCase):
    """验证数据库规则如何组成违禁判断计划。"""

    def setUp(self) -> None:
        self.config = {FORBIDDEN_CFG_GUIDELINE: "广告引流算违禁。"}
        self.store = FakeForbiddenStore(
            ["广告", "加群"],
            ["卖课私聊我 -> 是", "今天天气真好 -> 否"],
        )
        self.group_id = "123"

    def test_parse_yes_no_strict(self) -> None:
        self.assertEqual(parse_yes_no("是"), "yes")
        self.assertEqual(parse_yes_no("  否\n"), "no")
        self.assertEqual(parse_yes_no("是。"), "fail")
        self.assertEqual(parse_yes_no("不是"), "fail")
        self.assertEqual(parse_yes_no("是违禁"), "fail")
        self.assertEqual(parse_yes_no(""), "fail")

    def test_empty_text(self) -> None:
        plan = plan_forbidden_test(self.config, self.store, self.group_id, "   ")
        self.assertEqual(plan.status, "error")
        self.assertIn("请填写", plan.message)

    def test_no_trigger_words(self) -> None:
        plan = plan_forbidden_test(
            self.config,
            FakeForbiddenStore(),
            self.group_id,
            "广告来了",
        )
        self.assertEqual(plan.status, "error")
        self.assertIn("触发词", plan.message)

    def test_skip_without_trigger(self) -> None:
        plan = plan_forbidden_test(
            self.config, self.store, self.group_id, "今天天气不错"
        )
        self.assertEqual(plan.status, "skip")
        self.assertEqual(plan.trigger, "")
        self.assertEqual(plan.system, "")

    def test_ready_when_triggered(self) -> None:
        plan = plan_forbidden_test(self.config, self.store, self.group_id, "这里有广告")
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.trigger, "广告")
        self.assertEqual(plan.user, "这里有广告")
        self.assertIn("广告引流算违禁", plan.system)
        self.assertIn("卖课私聊我", plan.system)
        self.assertIn("只回答「是」或「否」", plan.system)

    def test_error_when_no_rule(self) -> None:
        plan = plan_forbidden_test(
            {},
            FakeForbiddenStore(["广告"]),
            self.group_id,
            "这里有广告",
        )
        self.assertEqual(plan.status, "error")
        self.assertEqual(plan.trigger, "广告")
        self.assertIn("违禁", plan.message)

    def test_payload_hides_prompt_and_webhook(self) -> None:
        plan = plan_forbidden_test(self.config, self.store, self.group_id, "这里有广告")
        payload = test_result_payload(plan, "yes")
        self.assertEqual(payload["status"], "yes")
        self.assertEqual(payload["trigger"], "广告")
        self.assertIn("不撤回", payload["message"])
        blob = str(payload)
        self.assertNotIn("system", blob)
        self.assertNotIn("webhook", blob.lower())
        self.assertNotIn("https://", blob)

    def test_payload_skip_keeps_message(self) -> None:
        plan = plan_forbidden_test(
            self.config, self.store, self.group_id, "今天天气不错"
        )
        payload = test_result_payload(plan, "skip")
        self.assertEqual(payload["status"], "skip")
        self.assertIn("未命中", payload["message"])


class ForbiddenCompleteTest(unittest.IsolatedAsyncioTestCase):
    """验证提供商回答只接受严格的是或否。"""

    async def test_yes_and_no(self) -> None:
        yes = await complete_yes_no(FakeProvider("是"), "sys", "user")
        no = await complete_yes_no(FakeProvider("否"), "sys", "user")
        self.assertEqual(yes, "yes")
        self.assertEqual(no, "no")

    async def test_messy_answer_is_fail(self) -> None:
        verdict = await complete_yes_no(FakeProvider("是的"), "sys", "user")
        self.assertEqual(verdict, "fail")

    async def test_provider_error_is_fail(self) -> None:
        verdict = await complete_yes_no(
            FakeProvider(error=RuntimeError("boom")),
            "sys",
            "user",
        )
        self.assertEqual(verdict, "fail")

    async def test_missing_provider_is_fail(self) -> None:
        self.assertEqual(await complete_yes_no(None, "sys", "user"), "fail")

    async def test_err_role_is_fail(self) -> None:
        class Broken:
            """模拟提供商以错误角色返回。"""

            async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
                """返回 role=err 的响应。"""
                return FakeResponse("是", role="err")

        self.assertEqual(await complete_yes_no(Broken(), "sys", "user"), "fail")
