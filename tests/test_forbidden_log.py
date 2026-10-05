# 违禁日志业务层：原因人话、原文采集、写库失败不影响处置。

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_action import apply_hit_actions
from astrbot_plugin_w1ndys_rules.business.forbidden_log import (
    collect_payload,
    reason_text,
)
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_REASON_GROUP_CARD,
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_MODEL,
    FORBIDDEN_REASON_QRCODE,
)


class Json:
    """AstrBot Json 组件替身。"""

    def __init__(self, data) -> None:
        self.data = data


class Image:
    """AstrBot Image 组件替身。"""

    def __init__(
        self, raw: object, boom: bool = False, async_mode: bool = False
    ) -> None:
        self.raw = raw
        self.boom = boom
        self.async_mode = async_mode

    def convert_to_base64(self):
        """命中时立刻转。失败抛错。async_mode 返回协程。"""
        # 模拟转码抛错，日志里只记失败
        if self.boom:
            raise RuntimeError("convert fail")
        # 有的 AstrBot 版本这里是协程
        if self.async_mode:
            return self._async_convert()
        return self.raw

    async def _async_convert(self):
        """给 async_mode 用的协程结果。"""
        return self.raw


class Plain:
    """普通文本段。"""

    def __init__(self, text: str) -> None:
        self.text = text


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
    def __init__(self, message_id=123, sender=None) -> None:
        self.message_id = message_id
        # 群消息的发送人资料；没有就当作读不到群昵称
        self.raw_message = None if sender is None else {"sender": sender}

class FakeEvent:
    def __init__(self, text: str = "", messages=None, sender=None) -> None:
        self.bot = FakeBot()
        self.message_obj = FakeMessage(sender=sender)
        self.message_str = text
        self._messages = messages or []

    def get_sender_id(self) -> str:
        return "10001"

    def get_self_id(self) -> str:
        return "999"

    def get_messages(self):
        return self._messages


class BoomLogStore(ForbiddenLogStore):
    """写入故意失败，用来确认撤回仍会发生。"""

    async def insert(self, *args, **kwargs) -> int:
        """永远失败。"""
        raise RuntimeError("db down")


class ReasonTextTest(unittest.TestCase):
    def test_known_codes(self) -> None:
        self.assertEqual(reason_text(FORBIDDEN_REASON_MODEL, "广告"), "文本模型命中：广告")
        self.assertEqual(reason_text(FORBIDDEN_REASON_GROUP_CARD, "群名片"), "群名片拦截")
        self.assertEqual(reason_text(FORBIDDEN_REASON_QRCODE, ""), "二维码直接违禁")
        self.assertEqual(
            reason_text(FORBIDDEN_REASON_IMAGE_MODEL, ""),
            "图片转写命中，模型判定是",
        )
        self.assertEqual(
            reason_text(FORBIDDEN_REASON_IMAGE_MODEL, "广告"),
            "图片转写命中：广告",
        )
        self.assertEqual(reason_text("other", "触发"), "触发")

    def test_appends_judge_reason(self) -> None:
        self.assertEqual(
            reason_text(FORBIDDEN_REASON_MODEL, "广告", "像招嫖"),
            "文本模型命中：广告：像招嫖",
        )



class CollectPayloadTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_json_images(self) -> None:
        """text 用 message_str；Json 原样；图去掉 base64://。"""
        event = FakeEvent(
            "这里有广告",
            [
                Plain("忽略"),
                Json({"prompt": "群名片"}),
                Image("base64://abc"),
                Image(""),
                Image("x", boom=True),
                Image("base64://zz", async_mode=True),
            ],
        )
        text, json_text, images = await collect_payload(event)
        self.assertEqual(text, "这里有广告")
        self.assertEqual(json.loads(json_text), [{"prompt": "群名片"}])
        items = json.loads(images)
        self.assertEqual(items[0], {"ok": True, "data": "abc"})
        self.assertEqual(items[1], {"ok": False})
        self.assertEqual(items[2], {"ok": False})
        self.assertEqual(items[3], {"ok": True, "data": "zz"})


class ApplyHitLogTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ForbiddenLogStore(Path(self._tmp.name) / "rules.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _hit(self, event, log_text=None) -> None:
        """按文本模型命中跑一次处置，只关心写进库的那条日志。"""
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0},
            "123",
            "广告",
            "这里有广告",
            log_store=self.store,
            reason_code=FORBIDDEN_REASON_MODEL,
            log_text=log_text,
        )

    def _last_row(self):
        """最新一条日志。三条昵称用例都只看这一行。"""
        items, _total = self.store.list_page("", "", "", 0, 10)
        return items[0]

    async def test_hit_writes_message_str_not_model_prompt(self) -> None:
        """飞书仍用传入 text，日志 text 列用 message_str。"""
        event = FakeEvent("这里有广告", [Json({"a": 1})])
        remind = await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0},
            "123",
            "广告",
            "模型提示词",
            log_store=self.store,
            reason_code=FORBIDDEN_REASON_MODEL,
        )
        self.assertEqual(remind, "")
        items, total = self.store.list_page("", "", "", 0, 10)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].text, "这里有广告")
        self.assertNotEqual(items[0].text, "模型提示词")
        self.assertEqual(items[0].reason_code, FORBIDDEN_REASON_MODEL)
        self.assertIn("广告", items[0].reason_text)

    async def test_insert_fail_still_recalls(self) -> None:
        """写日志失败不能挡住撤回。"""
        event = FakeEvent("这里有广告")
        boom = BoomLogStore(Path(self._tmp.name) / "boom.db")
        await apply_hit_actions(
            event,
            {FORBIDDEN_CFG_MUTE_SECONDS: 0},
            "123",
            "广告",
            "这里有广告",
            log_store=boom,
            reason_code=FORBIDDEN_REASON_MODEL,
        )
        actions = [name for name, _kwargs in event.bot.api.calls]
        self.assertEqual(actions, ["delete_msg", "get_group_msg_history"])


    async def test_hit_records_sender_name(self) -> None:
        """命中写日志带上当次群昵称，群名片优先。"""
        await self._hit(FakeEvent("这里有广告", sender={"card": "小明", "nickname": "nick"}))
        self.assertEqual(self._last_row().sender_name, "小明")

    async def test_hit_uses_nickname_without_card(self) -> None:
        """群名片为空时记 QQ 昵称。"""
        await self._hit(FakeEvent("这里有广告", sender={"nickname": "nick"}))
        self.assertEqual(self._last_row().sender_name, "nick")

    async def test_each_hit_keeps_its_own_name(self) -> None:
        """同一人换昵称再命中，只写新日志，旧日志里的昵称不动。"""
        await self._hit(FakeEvent("这里有广告", sender={"card": "小明"}))
        await self._hit(FakeEvent("这里有广告", sender={"card": "小刚"}))
        items, total = self.store.list_page("", "", "", 0, 10)
        self.assertEqual(total, 2)
        self.assertEqual(items[0].sender_name, "小刚")
        self.assertEqual(items[1].sender_name, "小明")

    async def test_log_text_overrides_message_str(self) -> None:
        """模型命中传了用户文本时，text 存这份文本而不是外层 message_str。"""
        event = FakeEvent("外层转发文本")
        await self._hit(event, log_text="送给模型的用户文本")
        self.assertEqual(self._last_row().text, "送给模型的用户文本")

    async def test_empty_log_text_stays_empty(self) -> None:
        """送审用户文本为空时 text 存空串，不回退到 message_str。"""
        event = FakeEvent("外层转发文本")
        await self._hit(event, log_text="")
        self.assertEqual(self._last_row().text, "")
