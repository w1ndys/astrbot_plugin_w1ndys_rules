# 图片路：二维码直接违禁；原图 OCR 有可见文字后走触发词，命中再送模型。

import sys
import tempfile
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
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_SAMPLES,
    QRCODE_HIT,
)

HIT = "截图里写着广告 加微 6m3p.cc"
NO_TRIGGER = "我都在6m3p.cc上面约的 全国随时随地都可以玩"



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
        plan = plan_image_test(ready_config(), "图片包含二维码", True, FakeStore())
        self.assertEqual(plan.status, "qr")
        self.assertEqual(plan.trigger, QRCODE_HIT)

    def test_describe_qr_without_trigger_skips(self) -> None:
        plan = plan_image_test(
            ready_config(), "图片包含二维码", False, FakeStore()
        )
        self.assertEqual(plan.status, "skip")

    def test_empty_skips(self) -> None:
        plan = plan_image_test(ready_config(), "  ", False, FakeStore())
        self.assertEqual(plan.status, "error")

    def test_no_trigger_skips(self) -> None:
        plan = plan_image_test(ready_config(), NO_TRIGGER, False, FakeStore())
        self.assertEqual(plan.status, "skip")
        self.assertEqual(plan.trigger, "")

    def test_trigger_in_ocr_is_ready(self) -> None:
        plan = plan_image_test(ready_config(), HIT, False, FakeStore())
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.trigger, "广告")
        self.assertNotIn("海报", plan.system)
        self.assertIn("招嫖引流算违禁。", plan.system)
        self.assertIn("可见文字", plan.user)


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
        )
        self.assertTrue(handled)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(event.bot.api.calls[0][0], "delete_msg")

    async def test_transcript_hits_with_trigger(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: HIT,
        )
        self.assertTrue(handled)

    async def test_no_trigger_skips_model(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: NO_TRIGGER,
        )
        self.assertFalse(handled)

    async def test_empty_transcript_skips(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: "",
        )
        self.assertFalse(handled)

    async def test_local_ocr_without_trigger_skips(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            ocr=lambda _data: NO_TRIGGER,
        )
        self.assertFalse(handled)

    async def test_local_ocr_with_trigger_hits(self) -> None:
        event = FakeEvent()
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            ocr=lambda _data: HIT,
        )
        self.assertTrue(handled)

    def _provider(self, text: str):
        async def get_provider():
            return FakeProvider(text)

        return get_provider

    async def test_transcript_hit_writes_model_user_text(self) -> None:
        """转写命中：日志文本存送审用户文本（含转写正文），不是外层 message_str。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        event = FakeEvent()
        event.message_str = "外层消息文本"
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: False,
            transcribe=lambda _event: HIT,
            log_store=store,
        )
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(total, 1)
        self.assertIn(HIT, items[0].text)
        self.assertNotIn("外层消息文本", items[0].text)

    async def test_qr_hit_still_writes_message_str(self) -> None:
        """二维码命中不请求模型，日志文本仍用外层 message_str。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        event = FakeEvent()
        event.message_str = "外层消息文本"
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: True,
            log_store=store,
        )
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].text, "外层消息文本")
