# 短视频抽帧：时长分界、抽取点数、跳过原因，以及抽帧后的二维码、OCR、模型顺序。

import base64
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business import forbidden_video
from astrbot_plugin_w1ndys_rules.business.forbidden_handle import (
    handle_forbidden_message,
)
from astrbot_plugin_w1ndys_rules.business.forbidden_video import (
    frame_count_for,
    handle_forbidden_videos,
    pick_timestamps,
    raw_video_meta,
    video_comps,
)
from astrbot_plugin_w1ndys_rules.data.blacklist_store import BlacklistStore
from astrbot_plugin_w1ndys_rules.data.forbidden_log_store import ForbiddenLogStore
from astrbot_plugin_w1ndys_rules.data.whitelist_store import WhitelistStore
from astrbot_plugin_w1ndys_rules.entity.constants import (
    CFG_FORBIDDEN_GROUPS,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_MUTE_SECONDS,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_QRCODE,
    SHORT_VIDEO_MAX_FILE_BYTES,
    SHORT_VIDEO_RANDOM_TRIES,
)

# 命中触发词的转写，和图片路测试用同一句，方便对照。
HIT = "截图里写着广告 加微 6m3p.cc"
# 没有触发词的转写。
NO_TRIGGER = "我都在6m3p.cc上面约的 全国随时随地都可以玩"
# 替身 runner 抽出来的假帧字节。二维码和 OCR 都不看内容，只要求非空。
FRAME_BYTES = b"PNG-FRAME"
# 抽帧用的假本地路径。替身 runner 不会真的读它。
VIDEO_PATH = "/tmp/rules-short-video.mp4"


class Video:
    """替身视频段：组件上只有文件方法，时长和大小不在组件上。"""

    def __init__(self, path: str = VIDEO_PATH, fail: bool = False) -> None:
        self.path = path
        self.fail = fail
        self.convert_calls = 0

    async def convert_to_file_path(self) -> str:
        """组件自己下载后的本地路径。下载失败时抛异常。"""
        self.convert_calls += 1
        # 模拟协议端缓存拿不到
        if self.fail:
            raise RuntimeError("download failed")
        return self.path


class Image:
    """替身图片段：图片路只用它的 base64。"""

    def __init__(self, raw: str = "YQ==") -> None:
        self.raw = raw

    def convert_to_base64(self) -> str:
        """图片路的 base64 原文。"""
        return self.raw


class File:
    """替身文件段：文件段里的 mp4 不检测。"""


class Plain:
    """替身文本段：不是视频段。"""


class FakeApi:
    """只记 OneBot 动作，不真的撤回禁言。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {}


class FakeBot:
    """只挂一个假协议端。"""

    def __init__(self) -> None:
        self.api = FakeApi()


class FakeMessage:
    """消息对象：raw_message 同时给 sender 和原始消息段数组。"""

    def __init__(self, role: str = "member", segments=None) -> None:
        self.message_id = 1
        self.raw_message = {"sender": {"role": role}, "message": segments or []}


class FakeEvent:
    """群消息替身：消息链给组件，原始数组给时长和文件大小。"""

    def __init__(self, messages=None, segments=None, role: str = "member") -> None:
        self.bot = FakeBot()
        self.message_obj = FakeMessage(role, segments)
        self.message_str = ""
        self._messages = [Video()] if messages is None else messages

    def get_messages(self):
        return self._messages

    def get_sender_id(self) -> str:
        return "10001"

    def get_self_id(self) -> str:
        return "999"


class FakeStore:
    """全局触发词表。"""

    def list_contents(self, group_id: str, kind: str) -> list[str]:
        return ["广告"]


class FakeReply:
    """模型返回：第一行是或否。"""

    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text
        self.role = "assistant"


class FakeProvider:
    """替身模型：记下调用次数和每次送审的用户文本。"""

    def __init__(self, text: str = "是") -> None:
        self.text = text
        self.calls = 0
        self.prompts: list = []

    async def text_chat(self, prompt=None, system_prompt=None, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        return FakeReply(self.text)


class FakeRunner:
    """替身抽帧工具：ffprobe 回时长，ffmpeg 回一帧字节，并记下每次命令。"""

    def __init__(self, duration: bytes = b"3.5", frame: bytes = FRAME_BYTES) -> None:
        self.duration = duration
        self.frame = frame
        self.commands: list = []

    def __call__(self, argv: list) -> bytes:
        self.commands.append(argv)
        # ffprobe 只问容器时长
        if argv[0] == "ffprobe":
            return self.duration
        return self.frame

    def extract_count(self) -> int:
        """ffmpeg 被调了几次，也就是真的抽了几帧。"""
        return len([argv for argv in self.commands if argv[0] == "ffmpeg"])


class MissingToolRunner:
    """替身 runner：装作本机没有 ffprobe 和 ffmpeg。"""

    def __call__(self, argv: list) -> bytes:
        raise FileNotFoundError(argv[0])


class CrowdedRandom:
    """替身随机函数：每次都抽同一个位置，间隔必然不达标，用于验证等分兜底。"""

    def __init__(self, value: float = 0.5) -> None:
        self.value = value
        self.calls = 0

    def __call__(self, _low: float, _high: float) -> float:
        self.calls += 1
        return self.value


def video_segment(duration=None, file_size=None) -> dict:
    """OneBot 数组格式的视频段。没给的字段就不写，模拟协议端省略。"""
    data = {}
    # 有时长才写这个键
    if duration is not None:
        data["duration"] = duration
    # 报过大小才写这个键
    if file_size is not None:
        data["file_size"] = file_size
    return {"type": "video", "data": data}


def ready_config(**extra) -> dict:
    """打开违禁的群配置，和图片路测试一致。"""
    data = {
        CFG_FORBIDDEN_GROUPS: ["123"],
        FORBIDDEN_CFG_GUIDELINE: "招嫖引流算违禁。",
        FORBIDDEN_CFG_SAMPLES: "约 + 网址 -> 是",
        FORBIDDEN_CFG_MUTE_SECONDS: 0,
        FORBIDDEN_CFG_REMIND_TEXT: "",
    }
    data.update(extra)
    return data


def provider_getter(provider):
    """把替身提供商包成入口层那样的异步取值函数。"""

    async def get_provider():
        return provider

    return get_provider


def decoder_without_code(_data):
    """替身解码器：没框也没载荷，代表这一帧没有码。"""
    return []


def seeded_random(seed: int = 7):
    """固定种子的随机函数，测试不靠真随机碰运气。"""
    return random.Random(seed).uniform


def plugin_logger_name() -> str:
    """插件日志的 logger 名。装了 AstrBot 时用它自己的 logger，否则是标准 logging 名。"""
    return getattr(forbidden_video._log, "name", "astrbot_plugin_w1ndys_rules")


def save_video_state() -> bool:
    """存下「本进程缺抽帧工具」这个标记，测完还原。"""
    return forbidden_video._tools_missing


def restore_video_state(saved: bool) -> None:
    """把缺抽帧工具的标记放回去，别把状态留给后面的测试。"""
    forbidden_video._tools_missing = saved


class VideoMetaTest(unittest.TestCase):
    """段收集和元信息：只收 Video，时长和大小从原始段读。"""

    def test_video_comps_only_video(self) -> None:
        """只收类型名 Video 的段，文件段和文本段都不抽。"""
        video = Video()
        comps = video_comps(FakeEvent(messages=[Plain(), video, File()]))
        self.assertEqual(comps, [video])

    def test_reads_meta_from_raw_segment(self) -> None:
        """时长和文件大小只在原始段上，组件上没有这两个字段。"""
        comp = Video()
        event = FakeEvent(
            messages=[comp],
            segments=[video_segment(duration="3.5", file_size="1048576")],
        )
        self.assertEqual(
            raw_video_meta(event, 0), {"duration": 3.5, "file_size": 1048576}
        )
        self.assertFalse(hasattr(comp, "duration"))

    def test_missing_segment_gives_empty_meta(self) -> None:
        """原始段数量对不上时返回空字典。"""
        event = FakeEvent(messages=[Video()], segments=[])
        self.assertEqual(raw_video_meta(event, 0), {})


class VideoFramePlanTest(unittest.TestCase):
    """抽帧数量和随机时间点。不依赖本机 ffmpeg。"""

    def test_four_seconds_still_extracts(self) -> None:
        """4.0 秒含边界，抽满 3 帧。"""
        self.assertEqual(frame_count_for(4.0), 3)

    def test_over_four_seconds_skips(self) -> None:
        """4.01 秒不抽帧。"""
        self.assertEqual(frame_count_for(4.01), 0)

    def test_unknown_duration_skips(self) -> None:
        """时长未知不抽帧。"""
        self.assertEqual(frame_count_for(None), 0)

    def test_frame_counts_by_duration(self) -> None:
        """0.5 秒 1 帧，1.5 秒 2 帧，3.5 秒 3 帧。"""
        self.assertEqual(frame_count_for(0.5), 1)
        self.assertEqual(frame_count_for(1.5), 2)
        self.assertEqual(frame_count_for(3.5), 3)

    def test_timestamp_count_follows_frames(self) -> None:
        """0.5 秒 1 个点，1.5 秒 2 个点，3.5 秒 3 个点。"""
        for duration, expected in ((0.5, 1), (1.5, 2), (3.5, 3)):
            stamps = pick_timestamps(duration, frame_count_for(duration), seeded_random())
            self.assertEqual(len(stamps), expected)

    def test_points_stay_inside_margin_and_spaced(self) -> None:
        """点落在 5% 到 95% 之间，相邻间隔不小于时长的 1/6。"""
        stamps = pick_timestamps(4.0, 3, seeded_random())
        self.assertEqual(len(stamps), 3)
        self.assertGreaterEqual(stamps[0], 0.2)
        self.assertLessEqual(stamps[-1], 3.8)
        self.assertGreaterEqual(stamps[1] - stamps[0], 4.0 / 6)
        self.assertGreaterEqual(stamps[2] - stamps[1], 4.0 / 6)

    def test_crowded_random_falls_back_to_even_points(self) -> None:
        """注入挤在一起的随机序列：重抽 8 次后落到等分点。"""
        crowded = CrowdedRandom()
        stamps = pick_timestamps(4.0, 2, crowded)
        self.assertEqual(stamps, [1.0, 3.0])
        self.assertEqual(crowded.calls, 2 * SHORT_VIDEO_RANDOM_TRIES)


class VideoHandleTest(unittest.IsolatedAsyncioTestCase):
    """抽帧判定：跳过原因、二维码优先、触发词门槛、只叫一次模型。"""

    def setUp(self) -> None:
        self._saved = save_video_state()

    def tearDown(self) -> None:
        restore_video_state(self._saved)

    async def test_no_video_returns_not_handled(self) -> None:
        """消息链里没有 Video 段就返回未处置。"""
        runner = FakeRunner()
        handled, remind = await handle_forbidden_videos(
            FakeEvent(messages=[Image()]),
            ready_config(),
            "123",
            provider_getter(FakeProvider()),
            runner=runner,
        )
        self.assertFalse(handled)
        self.assertEqual(remind, "")
        self.assertEqual(runner.commands, [])

    async def test_four_seconds_extracts(self) -> None:
        """4.0 秒进入抽帧，按帧数抽满 3 帧。"""
        runner = FakeRunner()
        comp = Video()
        event = FakeEvent(messages=[comp], segments=[video_segment(duration=4.0)])
        handled, _remind = await handle_forbidden_videos(
            event,
            ready_config(),
            "123",
            provider_getter(FakeProvider("否")),
            store=FakeStore(),
            decoder=decoder_without_code,
            ocr=lambda _data: NO_TRIGGER,
            runner=runner,
            random_fn=CrowdedRandom(),
        )
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 1)
        self.assertEqual(runner.extract_count(), 3)

    async def test_over_four_seconds_skips(self) -> None:
        """4.01 秒既不下载也不抽帧，并记下超时长。"""
        runner = FakeRunner()
        comp = Video()
        event = FakeEvent(messages=[comp], segments=[video_segment(duration=4.01)])
        with self.assertLogs(plugin_logger_name(), level="INFO") as captured:
            handled, _remind = await handle_forbidden_videos(
                event,
                ready_config(),
                "123",
                provider_getter(FakeProvider("是")),
                store=FakeStore(),
                runner=runner,
            )
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 0)
        self.assertEqual(runner.extract_count(), 0)
        self.assertTrue(any("reason=too_long" in line for line in captured.output))

    async def test_unknown_duration_skips(self) -> None:
        """原始段没写时长、ffprobe 也读不出来时不处置。"""
        runner = FakeRunner(duration=b"")
        event = FakeEvent(
            messages=[Video()], segments=[video_segment(file_size="1024")]
        )
        with self.assertLogs(plugin_logger_name(), level="INFO") as captured:
            handled, _remind = await handle_forbidden_videos(
                event,
                ready_config(),
                "123",
                provider_getter(FakeProvider("是")),
                store=FakeStore(),
                runner=runner,
            )
        self.assertFalse(handled)
        self.assertEqual(runner.extract_count(), 0)
        self.assertTrue(any("reason=no_duration" in line for line in captured.output))

    async def test_oversize_file_skips_download(self) -> None:
        """原始段报的大小超过 20MB 时不下载，也不抽帧。"""
        runner = FakeRunner()
        comp = Video()
        event = FakeEvent(
            messages=[comp],
            segments=[
                video_segment(duration=3.5, file_size=SHORT_VIDEO_MAX_FILE_BYTES + 1)
            ],
        )
        with self.assertLogs(plugin_logger_name(), level="INFO") as captured:
            handled, _remind = await handle_forbidden_videos(
                event,
                ready_config(),
                "123",
                provider_getter(FakeProvider("是")),
                store=FakeStore(),
                runner=runner,
            )
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 0)
        self.assertEqual(runner.extract_count(), 0)
        self.assertTrue(any("reason=too_large" in line for line in captured.output))

    async def test_missing_tool_skips_now_and_later(self) -> None:
        """缺 ffprobe 或 ffmpeg 时不处置，后面的短视频也不再试抽帧。"""
        event = FakeEvent(messages=[Video()], segments=[video_segment()])
        with self.assertLogs(plugin_logger_name(), level="INFO") as captured:
            handled, _remind = await handle_forbidden_videos(
                event,
                ready_config(),
                "123",
                provider_getter(FakeProvider("是")),
                store=FakeStore(),
                runner=MissingToolRunner(),
            )
        self.assertFalse(handled)
        self.assertTrue(forbidden_video._tools_missing)
        self.assertTrue(any("reason=tool_missing" in line for line in captured.output))

        later = FakeRunner()
        handled, _remind = await handle_forbidden_videos(
            FakeEvent(segments=[video_segment(duration=3.5)]),
            ready_config(),
            "123",
            provider_getter(FakeProvider("是")),
            store=FakeStore(),
            runner=later,
        )
        self.assertFalse(handled)
        self.assertEqual(later.extract_count(), 0)

    async def test_no_file_skips_segment(self) -> None:
        """本地文件拿不到就跳过这一段，不处置。"""
        comp = Video(fail=True)
        event = FakeEvent(messages=[comp], segments=[video_segment(duration=3.5)])
        with self.assertLogs(plugin_logger_name(), level="INFO") as captured:
            handled, _remind = await handle_forbidden_videos(
                event,
                ready_config(),
                "123",
                provider_getter(FakeProvider("是")),
                store=FakeStore(),
                runner=FakeRunner(),
            )
        self.assertFalse(handled)
        self.assertTrue(any("reason=no_file" in line for line in captured.output))

    async def test_qr_hit_skips_ocr_and_model(self) -> None:
        """任一帧检出二维码就按二维码处置，不再 OCR、不再叫模型。日志存该帧和解析内容。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        provider = FakeProvider("是")
        ocr_calls: list = []
        posted = []
        event = FakeEvent(segments=[video_segment(duration=3.5)])
        event.message_str = "外层消息文本"
        handled, _remind = await handle_forbidden_videos(
            event,
            ready_config(forbidden_feishu_webhook="https://example.com/hook"),
            "123",
            provider_getter(provider),
            log_store=store,
            decoder=lambda _data: ["https://qm.qq.com/q/frame"],
            ocr=ocr_calls.append,
            runner=FakeRunner(),
            poster=lambda url, body: posted.append((url, body)),
        )
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(ocr_calls, [])
        self.assertEqual(provider.calls, 0)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].reason_code, FORBIDDEN_REASON_QRCODE)
        self.assertIn("来源：短视频抽帧", items[0].text)
        self.assertIn("二维码内容：https://qm.qq.com/q/frame", items[0].text)
        self.assertIn(base64.b64encode(FRAME_BYTES).decode("ascii"), items[0].images)
        feishu = posted[0][1]["content"]["text"]
        self.assertIn("来源：短视频抽帧", feishu)
        self.assertIn("二维码内容：https://qm.qq.com/q/frame", feishu)

    async def test_transcript_without_trigger_skips_model(self) -> None:
        """帧都干净且转写没命中触发词时不叫模型。"""
        provider = FakeProvider("是")
        event = FakeEvent(segments=[video_segment(duration=3.5)])
        handled, _remind = await handle_forbidden_videos(
            event,
            ready_config(),
            "123",
            provider_getter(provider),
            store=FakeStore(),
            decoder=decoder_without_code,
            ocr=lambda _data: NO_TRIGGER,
            runner=FakeRunner(),
        )
        self.assertFalse(handled)
        self.assertEqual(provider.calls, 0)

    async def test_trigger_yes_calls_model_once_with_video_source(self) -> None:
        """转写命中触发词且模型说是时只叫一次，送审文本写明来源是短视频抽帧。"""
        tmp = tempfile.TemporaryDirectory()
        store = ForbiddenLogStore(Path(tmp.name) / "rules.db")
        provider = FakeProvider("是")
        event = FakeEvent(segments=[video_segment(duration=3.5)])
        handled, _remind = await handle_forbidden_videos(
            event,
            ready_config(),
            "123",
            provider_getter(provider),
            store=FakeStore(),
            log_store=store,
            decoder=decoder_without_code,
            ocr=lambda _data: HIT,
            runner=FakeRunner(),
        )
        items, total = store.list_page("", "", "", 0, 10)
        tmp.cleanup()
        self.assertTrue(handled)
        self.assertEqual(provider.calls, 1)
        self.assertTrue(provider.prompts[0].startswith("来源: 短视频抽帧"))
        self.assertIn("二维码: 未检出", provider.prompts[0])
        self.assertEqual(total, 1)
        self.assertEqual(items[0].reason_code, FORBIDDEN_REASON_IMAGE_MODEL)
        self.assertTrue(items[0].text.startswith("来源: 短视频抽帧"))
        self.assertIn(HIT, items[0].text)

    async def test_model_no_keeps_message(self) -> None:
        """模型第一行是否时不处置。"""
        provider = FakeProvider("否")
        event = FakeEvent(segments=[video_segment(duration=3.5)])
        handled, remind = await handle_forbidden_videos(
            event,
            ready_config(),
            "123",
            provider_getter(provider),
            store=FakeStore(),
            decoder=decoder_without_code,
            ocr=lambda _data: HIT,
            runner=FakeRunner(),
        )
        self.assertFalse(handled)
        self.assertEqual(remind, "")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(event.bot.api.calls, [])


class VideoGateTest(unittest.IsolatedAsyncioTestCase):
    """跳过条件对短视频同样生效，图片路已处置时不抽帧。"""

    def setUp(self) -> None:
        self._saved = save_video_state()

    def tearDown(self) -> None:
        restore_video_state(self._saved)

    async def test_switch_off_never_extracts(self) -> None:
        """本群没开违禁时不下载视频。"""
        comp = Video()
        event = FakeEvent(messages=[comp], segments=[video_segment(duration=3.5)])
        handled, _reply = await handle_forbidden_message(
            ready_config(**{CFG_FORBIDDEN_GROUPS: []}),
            FakeStore(),
            event,
            "123",
            "",
            provider_getter(FakeProvider("是")),
        )
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 0)

    async def test_staff_never_extracts(self) -> None:
        """群主或管理员的消息不抽帧。"""
        comp = Video()
        event = FakeEvent(
            messages=[comp], segments=[video_segment(duration=3.5)], role="owner"
        )
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            provider_getter(FakeProvider("是")),
        )
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 0)

    async def test_whitelist_never_extracts(self) -> None:
        """本群白名单命中的发言人不抽帧。"""
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "rules.db"
        whitelist = WhitelistStore(db_path)
        blacklist = BlacklistStore(db_path)
        await whitelist.add("123", "10001")
        comp = Video()
        event = FakeEvent(messages=[comp], segments=[video_segment(duration=3.5)])
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            provider_getter(FakeProvider("是")),
            whitelist=whitelist,
            blacklist=blacklist,
        )
        tmp.cleanup()
        self.assertFalse(handled)
        self.assertEqual(comp.convert_calls, 0)

    async def test_image_hit_skips_video(self) -> None:
        """图片路已经处置时不去下载同一条消息里的视频。"""
        video = Video()
        event = FakeEvent(
            messages=[Image(), video], segments=[video_segment(duration=3.5)]
        )
        handled, _reply = await handle_forbidden_message(
            ready_config(),
            FakeStore(),
            event,
            "123",
            "",
            provider_getter(FakeProvider("是")),
            decoder=lambda _data: True,
        )
        self.assertTrue(handled)
        self.assertEqual(video.convert_calls, 0)
