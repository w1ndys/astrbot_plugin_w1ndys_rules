# 图片路：二维码直接违禁；转写规则门后才送模型。不走近 7 天活跃豁免。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_handle import (
    handle_forbidden_message,
)
from astrbot_plugin_w1ndys_rules.business.forbidden_image import plan_image_test
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_SAMPLES,
    QRCODE_HIT,
)

LEAK = "我都在6m3p.cc上面约的 全国随时随地都可以玩"


class Image:
    def __init__(self, raw: str = "YQ==") -> None:
        self.raw = raw


    def convert_to_base64(self):
        return self.raw


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {}


class FakeBot:
    def __init__(self) -> None:
        self.api = FakeApi()


class FakeMessage:
    def __init__(self) -> None:
        self.message_id = 1
        self.raw_message = {"sender": {"role": "member"}}


class FakeEvent:
    def __init__(self, messages=None, role: str = "member") -> None:
        self.bot = FakeBot()
        self.message_obj = FakeMessage()
        self.message_obj.raw_message = {"sender": {"role": role}}
        self.message_str = ""
        self._messages = messages or [Image()]

    def get_sender_id(self) -> str:
        return "10001"

    def get_self_id(self) -> str:
        return "999"

    def get_messages(self):
        return self._messages


class FakeStore:
    def list_contents(self, group_id: str, kind: str) -> list[str]:
        return ["广告"]


class FakeActivity:
    def is_within_window(self, group_id: str, user_id: str) -> bool:
        return True


class FakeProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        self.calls += 1
        return FakeReply(self.text)


class FakeReply:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text
        self.role = "assistant"


def ready_config() -> dict:
    return {
        CFG_FORBIDDEN_GROUPS: ["123"],
        FORBIDDEN_CFG_GUIDELINE: "招嫖引流算违禁。",
        FORBIDDEN_CFG_SAMPLES: "约 + 网址 -> 是",
        FORBIDDEN_CFG_MUTE_SECONDS: 0,
    }


class ImagePlanTest(unittest.TestCase):
    def test_qr_skips_model(self) -> None:
        plan = plan_image_test(ready_config(), "图片包含二维码", True)
        self.assertEqual(plan.status, "qr")
        self.assertEqual(plan.trigger, QRCODE_HIT)

    def test_describe_qr_is_not_qr_layer(self) -> None:
        plan = plan_image_test(ready_config(), "图片包含二维码", False)
        self.assertEqual(plan.status, "skip")

    def test_leak_is_ready(self) -> None:
        plan = plan_image_test(ready_config(), LEAK, False)
        self.assertEqual(plan.status, "ready")
        self.assertIn("6m3p.cc", plan.user)


class ImageHandleTest(unittest.IsolatedAsyncioTestCase):
    async def test_qr_recalls_without_model(self) -> None:
        event = FakeEvent()
        provider = FakeProvider("是")

        async def get_provider():
            return provider

        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            get_provider,
            decoder=lambda data: True,
            activity=FakeActivity(),
        )
        self.assertTrue(handled)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(event.bot.api.calls[0][0], "delete_msg")

    async def test_transcript_hits_even_if_active(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: LEAK,
            activity=FakeActivity(),
        )
        self.assertTrue(handled)

    async def test_dinner_skips(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: "晚上约饭",
        )
        self.assertFalse(handled)

    def _provider(self, text: str):
        async def get_provider():
            return FakeProvider(text)

        return get_provider
