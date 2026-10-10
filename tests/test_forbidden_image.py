# 图片路：二维码直接违禁；原图 OCR 有可见文字后走触发词，命中再送模型。

import base64
import inspect
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business import forbidden_ocr, forbidden_qr
from astrbot_plugin_w1ndys_rules.business.forbidden_handle import (
    handle_forbidden_message,
)
from astrbot_plugin_w1ndys_rules.business.forbidden_image import (
    GIF_OCR_NOTE,
    inspect_uploaded_image,
    plan_image_test,
)
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_SAMPLES,
    IMAGE_TEST_MAX_BYTES,
    PLUGIN_NAME,
    QRCODE_HIT,
)
from astrbot_plugin_w1ndys_rules.main import RulesPlugin

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
        """二维码命中不请求模型。日志保留外层消息，并附来源、解析内容和命中图。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        event = FakeEvent()
        event.message_str = "外层消息文本"
        posted = []
        posted = []
        config = ready_config()
        config[FORBIDDEN_CFG_FEISHU_WEBHOOK] = "https://example.com/hook"
        handled, _reply = await handle_forbidden_message(
            config,
            FakeStore(),
            event,
            "123",
            "",
            self._provider("是"),
            decoder=lambda data: ["https://qm.qq.com/q/abc"],
            log_store=store,
            poster=lambda url, body: posted.append((url, body)),
        )
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(total, 1)
        self.assertIn("外层消息文本", items[0].text)
        self.assertIn("来源：图片", items[0].text)
        self.assertIn("二维码内容：https://qm.qq.com/q/abc", items[0].text)
        self.assertIn("YQ==", items[0].images)
        feishu = posted[0][1]["content"]["text"]
        self.assertIn("来源：图片", feishu)
        self.assertIn("二维码内容：https://qm.qq.com/q/abc", feishu)


# sys.modules 里原本没有这个键时记下的哨兵，还原时按它决定删不删
_MISSING = object()


def _restore_module(name: str, saved: object) -> None:
    """还原包状态。原本没装的键要删掉，别把假模块留给后面的测试。"""
    # 单测环境本来就没有这个键，删掉即还原
    if saved is _MISSING:
        sys.modules.pop(name, None)
        return
    sys.modules[name] = saved


def save_engine_state() -> tuple:
    """存下二维码三层、OCR 引擎缓存和本机包状态，测完还原。"""
    return (
        forbidden_qr._wechat,
        forbidden_qr._wechat_state,
        forbidden_qr._zxing,
        forbidden_qr._zxing_state,
        forbidden_qr._qreader,
        forbidden_qr._qreader_state,
        forbidden_qr._bgr_from_bytes,
        forbidden_qr._bgr_to_rgb,
        forbidden_ocr._engine,
        forbidden_ocr._engine_failed,
        forbidden_ocr._engine_init_failed,
        sys.modules.get("cv2", _MISSING),
        sys.modules.get("cv2.wechat_qrcode", _MISSING),
        sys.modules.get("zxingcpp", _MISSING),
        sys.modules.get("qreader", _MISSING),
        sys.modules.get("rapidocr", _MISSING),
        sys.modules.get("rapidocr_onnxruntime", _MISSING),
    )


def restore_engine_state(saved: tuple) -> None:
    """把引擎缓存和包状态放回去。"""
    (
        forbidden_qr._wechat,
        forbidden_qr._wechat_state,
        forbidden_qr._zxing,
        forbidden_qr._zxing_state,
        forbidden_qr._qreader,
        forbidden_qr._qreader_state,
        forbidden_qr._bgr_from_bytes,
        forbidden_qr._bgr_to_rgb,
        forbidden_ocr._engine,
        forbidden_ocr._engine_failed,
        forbidden_ocr._engine_init_failed,
        cv2_module,
        cv2_wechat_module,
        zxing_module,
        qreader_module,
        rapidocr_module,
        rapidocr_old_module,
    ) = saved
    _restore_module("cv2", cv2_module)
    _restore_module("cv2.wechat_qrcode", cv2_wechat_module)
    _restore_module("zxingcpp", zxing_module)
    _restore_module("qreader", qreader_module)
    _restore_module("rapidocr", rapidocr_module)
    _restore_module("rapidocr_onnxruntime", rapidocr_old_module)


def hide_local_engines() -> None:
    """藏掉本机引擎包并清缓存。测试不加载真模型，也不依赖本机装了什么。"""
    # 三层都要藏，装上 contrib 或 zxing-cpp 的机器才有可能走到真实导入
    forbidden_qr._wechat = None
    forbidden_qr._wechat_state = ""
    forbidden_qr._zxing = None
    forbidden_qr._zxing_state = ""
    forbidden_qr._qreader = None
    forbidden_qr._qreader_state = ""
    forbidden_ocr._engine = None
    forbidden_ocr._engine_failed = False
    forbidden_ocr._engine_init_failed = False
    # 置 None 会让后续 import 抛 ImportError，等效于这台机器没装
    sys.modules["cv2"] = None
    sys.modules["cv2.wechat_qrcode"] = None
    sys.modules["zxingcpp"] = None
    sys.modules["qreader"] = None
    sys.modules["rapidocr"] = None
    sys.modules["rapidocr_onnxruntime"] = None


def provider_getter(provider):
    """把替身提供商包成入口层那样的异步取值函数。"""

    async def get_provider():
        """返回注入的提供商。"""
        return provider

    return get_provider


def decoder_without_code(_data):
    """替身解码器：没框也没载荷，代表这张图没有码。"""
    return []


def reader_without_text(_data):
    """替身 OCR：这张图没认出字。"""
    return ""


def gif_bytes() -> bytes:
    """gif 文件头加几个填充字节，够判断格式就行。"""
    return b"GIF89a" + b"\x00" * 8


class UploadedImageInspectTest(unittest.IsolatedAsyncioTestCase):
    """图片检测测试业务：结论只认本机引擎，调用方塞不进 qr_found。"""

    def setUp(self) -> None:
        self._saved = save_engine_state()
        hide_local_engines()

    def tearDown(self) -> None:
        restore_engine_state(self._saved)

    def test_signature_has_no_qr_found(self) -> None:
        """签名里没有 qr_found，请求体塞不进结论。"""
        names = list(inspect.signature(inspect_uploaded_image).parameters)
        self.assertEqual(
            names, ["config", "store", "data", "decoder", "ocr", "get_provider"]
        )

    async def test_decoder_without_code_is_not_found(self) -> None:
        """注入无码解码器：引擎跑过报 ready，检出仍为否。"""
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"uploaded-image",
            decoder=decoder_without_code,
            ocr=reader_without_text,
        )
        self.assertEqual(result["qr"]["engine"], "ready")
        self.assertFalse(result["qr"]["found"])
        self.assertFalse(result["llm_called"])

    async def test_no_trigger_keeps_llm_off(self) -> None:
        """转写没命中触发词就不叫模型。"""
        provider = FakeProvider("是")
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"uploaded-image",
            decoder=decoder_without_code,
            ocr=lambda _data: NO_TRIGGER,
            get_provider=provider_getter(provider),
        )
        self.assertEqual(result["plan_status"], "skip")
        self.assertFalse(result["llm_called"])
        self.assertEqual(result["verdict"], "")
        self.assertEqual(provider.calls, 0)

    async def test_trigger_calls_model_once(self) -> None:
        """命中触发词只叫一次模型，文案沿用大模型测试页那套。"""
        provider = FakeProvider("是")
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"uploaded-image",
            decoder=decoder_without_code,
            ocr=lambda _data: HIT,
            get_provider=provider_getter(provider),
        )
        self.assertTrue(result["llm_called"])
        self.assertEqual(result["verdict"], "yes")
        self.assertEqual(result["trigger"], "广告")
        self.assertEqual(provider.calls, 1)
        self.assertIn("是违禁", result["message"])

    async def test_missing_provider_keeps_qr_and_ocr(self) -> None:
        """没有对话提供商：模型不跑，二维码和 OCR 字段仍返回。"""

        async def no_provider():
            """当前没有可用提供商。"""
            return None

        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"uploaded-image",
            decoder=decoder_without_code,
            ocr=lambda _data: HIT,
            get_provider=no_provider,
        )
        self.assertFalse(result["llm_called"])
        self.assertEqual(result["verdict"], "")
        self.assertIn("提供商", result["message"])
        self.assertEqual(result["qr"]["engine"], "ready")
        self.assertEqual(result["ocr"]["text"], HIT)

    async def test_engine_missing_is_not_found(self) -> None:
        """引擎没装时报 missing，检出必须为否，不能显示成已识别且无码。"""
        # 这组字节本来解不出图，诊断会停在坏图那一步；给解码替身才真的去试三级
        forbidden_qr._bgr_from_bytes = lambda _data: object()
        result = await inspect_uploaded_image(
            ready_config(), FakeStore(), b"uploaded-image"
        )
        self.assertEqual(result["qr"]["engine"], "missing")
        self.assertFalse(result["qr"]["found"])
        self.assertEqual(result["qr"]["layer"], "")
        self.assertEqual(result["qr"]["wechat"], "missing")
        self.assertEqual(result["ocr"]["engine"], "missing")

    async def test_empty_bytes_skips_engines(self) -> None:
        """空字节不喂引擎，直接报错状态。"""
        calls = []
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"",
            decoder=calls.append,
            ocr=calls.append,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["plan_status"], "error")
        self.assertEqual(result["qr"], {})
        self.assertIn("没有收到图片", result["message"])

    async def test_oversize_bytes_skips_engines(self) -> None:
        """超过 8MB 不喂引擎，直接报错状态。"""
        calls = []
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"x" * (IMAGE_TEST_MAX_BYTES + 1),
            decoder=calls.append,
            ocr=calls.append,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["plan_status"], "error")
        self.assertIn("8MB", result["message"])

    async def test_gif_gets_ocr_note(self) -> None:
        """gif 仍跑识别，但要把热路径不跑 OCR 这条差别写给页面。"""
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            gif_bytes(),
            decoder=decoder_without_code,
            ocr=reader_without_text,
        )
        self.assertEqual(result["note"], GIF_OCR_NOTE)

    async def test_png_has_no_gif_note(self) -> None:
        """不是 gif 就不加这条说明，免得页面误导。"""
        result = await inspect_uploaded_image(
            ready_config(),
            FakeStore(),
            b"\x89PNG\r\n\x1a\n",
            decoder=decoder_without_code,
            ocr=reader_without_text,
        )
        self.assertNotIn("note", result)


class FakeWebResponse:
    """假响应：入口只用到状态码和 JSON 体。"""

    def __init__(self, payload, status_code: int) -> None:
        self.status_code = status_code
        self.body = json.dumps(payload).encode("utf-8")


def _fake_json_response(data=None, *, status_code=200, headers=None):
    """假成功响应：把入口给的对象收进 body。"""
    return FakeWebResponse(data, status_code)


def _fake_error_response(message, *, status_code=400, data=None, headers=None):
    """假错误响应：页面只看状态码和文案。"""
    return FakeWebResponse({"message": message}, status_code)


def build_fake_web() -> object:
    """造一个假的 astrbot.api.web。入口在调用时才导入它，所以运行期换掉整个模块。"""
    fake = types.ModuleType("astrbot.api.web")
    fake.request = FakeWebRequest({})
    fake.json_response = _fake_json_response
    fake.error_response = _fake_error_response
    return fake


class FakeWebRequest:
    """假请求：只回答最近一次塞进来的请求体。"""

    def __init__(self, payload) -> None:
        self.payload = payload

    async def json(self, default=None):
        """入口读请求体时返回固定内容。"""
        return self.payload


class FakeWebContext:
    """假上下文：只记注册过的接口路径，也不给对话提供商。"""

    def __init__(self) -> None:
        self.paths = []

    def register_web_api(self, path, _handler, _methods, _name) -> None:
        """入口注册接口时把路径记下来。"""
        self.paths.append(path)

    async def get_using_provider_async(self):
        """当前没有可用对话提供商。"""
        return None


class EntryImageTestApiTest(unittest.IsolatedAsyncioTestCase):
    """入口层：请求体只取图片，qr_found 不进结论，坏请求回 400。"""

    def setUp(self) -> None:
        self._saved = save_engine_state()
        hide_local_engines()
        # 入口在调用时才导入 astrbot.api.web，直接换掉整个模块比补属性稳
        self._saved_web = sys.modules.get("astrbot.api.web", _MISSING)
        self.web_api = build_fake_web()
        sys.modules["astrbot.api.web"] = self.web_api
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin.settings = ready_config()
        self.plugin.forbidden = FakeStore()
        self.plugin.context = FakeWebContext()

    def tearDown(self) -> None:
        _restore_module("astrbot.api.web", self._saved_web)
        restore_engine_state(self._saved)

    def test_registers_image_test_path(self) -> None:
        """注册的地址要和页面写的一致，否则按钮打到 404。"""
        self.plugin._register_forbidden_page()
        self.assertIn(f"/{PLUGIN_NAME}/forbidden/image-test", self.plugin.context.paths)

    async def test_body_qr_found_is_ignored(self) -> None:
        """请求体带 qr_found=true，响应仍以本机解码为准。"""
        body = {
            "image_base64": self._data_url(b"uploaded-image"),
            "qr_found": True,
        }
        response = await self._post(body)
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["qr"]["found"])
        self.assertFalse(payload["llm_called"])

    async def test_plain_base64_without_prefix_works(self) -> None:
        """不带 data URL 前缀的 base64 也要能过。"""
        body = {"image_base64": base64.b64encode(b"uploaded-image").decode()}
        response = await self._post(body)
        self.assertEqual(response.status_code, 200)

    async def test_bad_base64_returns_400(self) -> None:
        """坏 base64 回 400，不启动引擎。"""
        response = await self._post({"image_base64": "!!!不是 base64!!!"})
        self.assertEqual(response.status_code, 400)

    async def test_oversize_body_returns_400(self) -> None:
        """解码后超过 8MB 回 400。"""
        big = base64.b64encode(b"x" * (IMAGE_TEST_MAX_BYTES + 1)).decode()
        response = await self._post({"image_base64": big})
        self.assertEqual(response.status_code, 400)

    def _data_url(self, data: bytes) -> str:
        """页面用 FileReader 提交的就是这种带前缀的 data URL。"""
        return "data:image/png;base64," + base64.b64encode(data).decode()

    async def _post(self, body):
        """把请求体塞进假 request 后调一次接口，拿状态码和 JSON 体。"""
        self.web_api.request = FakeWebRequest(body)
        return await self.plugin.page_forbidden_image_test()
