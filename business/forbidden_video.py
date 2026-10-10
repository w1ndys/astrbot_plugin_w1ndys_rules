# 业务层：短视频抽帧路。4.0 秒以内的 Video 段抽帧后交给现有二维码、OCR 和是/否模型。
# 超时长、时长未知、文件过大、缺抽帧工具都只记原因，不处置。
# 帧走 ffmpeg 管道输出字节，本功能不写临时帧文件，所以没有要删的帧文件；协议端缓存也不动。

import inspect
import random
import subprocess

try:
    from astrbot.api import logger as _log
except ImportError:
    # 单测不装 AstrBot，落到标准 logging
    import logging

    _log = logging.getLogger("astrbot_plugin_w1ndys_rules")

from ..entity.constants import (
    FORBIDDEN_REASON_IMAGE_MODEL,
    FORBIDDEN_REASON_QRCODE,
    QRCODE_HIT,
    SHORT_VIDEO_EVEN_RATIOS,
    SHORT_VIDEO_FRAME_SPLIT_MID,
    SHORT_VIDEO_FRAME_SPLIT_SHORT,
    SHORT_VIDEO_MAX_FILE_BYTES,
    SHORT_VIDEO_MAX_FRAMES,
    SHORT_VIDEO_MAX_SECONDS,
    SHORT_VIDEO_MIN_GAP_RATIO,
    SHORT_VIDEO_RANDOM_TRIES,
    SHORT_VIDEO_SAMPLE_MARGIN,
    SHORT_VIDEO_TOOL_TIMEOUT_SECONDS,
)
from .forbidden_action import apply_hit_actions
from .forbidden_image import plan_image_test
from .forbidden_judge import complete_yes_no
from .forbidden_ocr import ocr_text_from_bytes
from .forbidden_qr import qr_found_in_bytes

# 消息链里短视频段的类型名。合并转发段和文件段（mp4）都不是这个名字，因此不会被抽帧。
_VIDEO_COMP_NAME = "Video"
# OneBot 原始数组里视频段的 type 值。时长和文件大小只在原始段上，组件上读不到。
_RAW_VIDEO_TYPE = "video"
# 读容器时长用 ffprobe，抽单帧用 ffmpeg。两个命令都通过可注入的 runner 调用。
_PROBE_CMD = "ffprobe"
_FRAME_CMD = "ffmpeg"
_PROBE_ENTRY = "format=duration"
# 本进程是否已经确认缺 ffprobe 或 ffmpeg。缺了就不再抽帧，避免每条消息都失败一次。
_tools_missing = False

def video_comps(event: object) -> list:
    """消息链里类型名 Video 的段。合并转发里的视频和文件段 mp4 都不在这里。"""
    getter = getattr(event, "get_messages", None)
    # 残缺事件没有消息链
    if not callable(getter):
        return []
    items = []
    for comp in getter() or []:
        # 只收 Video 段，文件段的 mp4 不检测
        if type(comp).__name__ == _VIDEO_COMP_NAME:
            items.append(comp)
    return items

def raw_video_meta(event: object, index: int) -> dict:
    """原始消息段上的 duration 和 file_size。

    AstrBot 的 Video 是 pydantic 模型，协议端多出来的这两个字段会被丢掉，
    所以只能按视频段在原始数组里的位置去读。读不到的键就不出现。
    """
    segments = _raw_video_segments(event)
    # 原始段数量对不上，说明这条消息没有可用的视频原始段
    if index < 0 or index >= len(segments):
        return {}
    data = segments[index]
    meta = {}
    duration = _positive_seconds(data.get("duration"))
    # 有时长才写进结果
    if duration is not None:
        meta["duration"] = duration
    size = _positive_int(data.get("file_size"))
    # 报过文件大小才写进结果
    if size is not None:
        meta["file_size"] = size
    return meta

def probe_duration_seconds(path: str, runner=None) -> float | None:
    """用 ffprobe 读容器时长。非数字、非正数、超时都返回 None。

    命令不在 PATH 时抛 FileNotFoundError，好让调用方记一次工具缺失。
    """
    run = runner or _run_tool
    argv = [_PROBE_CMD, "-v", "error", "-show_entries", _PROBE_ENTRY, "-of", "csv=p=0", path]
    return _positive_seconds(_tool_output(run, argv))

def frame_count_for(duration: float) -> int:
    """按时长决定抽几帧。时长不可用或超过 4.0 秒返回 0，表示不抽。"""
    # 时长未知、非正数或超过上限都不抽帧
    if not duration or duration <= 0 or duration > SHORT_VIDEO_MAX_SECONDS:
        return 0
    # 不足 0.8 秒只有一屏内容，多抽也是同一画面
    if duration < SHORT_VIDEO_FRAME_SPLIT_SHORT:
        return 1
    # 不足 2.0 秒画面变化少，两帧够看
    if duration < SHORT_VIDEO_FRAME_SPLIT_MID:
        return 2
    return SHORT_VIDEO_MAX_FRAMES

def pick_timestamps(duration: float, count: int, random_fn=None) -> list:
    """在时长的 5% 到 95% 之间取 count 个点，相邻间隔至少为时长的 1/6。

    随机点挤在一起就重抽，次数用完改用该帧数下的等分点。测试注入 random_fn。
    """
    # 没有时长或没有帧数就取不出点
    if not duration or duration <= 0 or count <= 0:
        return []
    rand = random_fn or random.uniform
    low = duration * SHORT_VIDEO_SAMPLE_MARGIN
    high = duration - low
    gap = duration * SHORT_VIDEO_MIN_GAP_RATIO
    for _attempt in range(SHORT_VIDEO_RANDOM_TRIES):
        points = [float(rand(low, high)) for _index in range(count)]
        # 排得开就用这一组随机点
        if _spaced_enough(points, gap):
            return sorted(points)
    return _even_points(duration, count)

def extract_png(path: str, timestamp: float, runner=None) -> bytes:
    """按时间点抽一帧 PNG 字节。超时和坏视频返回空字节。

    不取视频封面：封面可以由发送方换成无关图。命令不在 PATH 时抛 FileNotFoundError。
    """
    run = runner or _run_tool
    argv = [
        _FRAME_CMD,
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        path,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    return _tool_output(run, argv)

async def handle_forbidden_videos(
    event: object,
    config: object,
    group_id: str,
    get_provider,
    poster=None,
    log_store=None,
    decoder=None,
    ocr=None,
    store=None,
    mute_store=None,
    runner=None,
    random_fn=None,
) -> tuple[bool, str]:
    """短视频路：抽帧后先二维码，再 OCR 过触发词，命中才送一次模型。没有视频返回未处置。"""
    comps = video_comps(event)
    # 没有 Video 段就没有短视频可抽
    if not comps:
        return False, ""
    # 本进程已经确认缺抽帧工具，后面所有短视频都不再试
    if _tools_missing:
        _log.info("[rules] video skip group=%s reason=tool_missing", group_id)
        return False, ""
    _log.info("[rules] video start group=%s comps=%s", group_id, len(comps))
    frames = await _collect_frames(event, comps, runner, random_fn)
    # 一帧都没抽出来（超时长、时长未知、文件过大、坏视频）就不处置
    if not frames:
        _log.info("[rules] video skip group=%s reason=no_frame", group_id)
        return False, ""
    return await _judge_frames(
        event,
        config,
        group_id,
        get_provider,
        frames,
        poster,
        log_store,
        decoder,
        ocr,
        store,
        mute_store,
    )

async def _judge_frames(
    event: object,
    config: object,
    group_id: str,
    get_provider,
    frames: list,
    poster,
    log_store,
    decoder,
    ocr,
    store,
    mute_store,
) -> tuple[bool, str]:
    """帧的判定顺序：任一帧有条码就处置；都干净才转写、过触发词、叫一次模型。"""
    for frame in frames:
        # 任一帧检出二维码就直接处置，不再认字也不再叫模型
        if qr_found_in_bytes(frame, decoder):
            _log.info("[rules] video qr hit group=%s", group_id)
            remind = await apply_hit_actions(
                event,
                config,
                group_id,
                QRCODE_HIT,
                QRCODE_HIT,
                poster,
                log_store,
                FORBIDDEN_REASON_QRCODE,
                mute_store=mute_store,
            )
            return True, remind
    transcript = _frames_transcript(frames, ocr)
    plan = plan_image_test(config, transcript, False, store)
    # 空转写、没触发词或没设定都不叫模型
    if plan.status != "ready":
        _log.info(
            "[rules] video skip group=%s status=%s msg=%s",
            group_id,
            plan.status,
            plan.message,
        )
        return False, ""
    user = _video_user(transcript)
    provider = await get_provider()
    judged = await complete_yes_no(provider, plan.system, user)
    # 只有第一行「是」才处置，否和乱答都不动
    if judged.verdict != "yes":
        _log.info("[rules] video verdict group=%s verdict=%s", group_id, judged.verdict)
        return False, ""
    remind = await apply_hit_actions(
        event,
        config,
        group_id,
        plan.trigger,
        user,
        poster,
        log_store,
        FORBIDDEN_REASON_IMAGE_MODEL,
        judged.reason,
        mute_store=mute_store,
        # 视频转写命中也存送审用户文本（含转写正文），和飞书「消息」同一份
        log_text=user,
    )
    _log.info("[rules] video model hit group=%s trigger=%s", group_id, plan.trigger)
    return True, remind

async def _collect_frames(event: object, comps: list, runner, random_fn) -> list:
    """逐段抽帧。缺抽帧工具就整条消息都不抽，其它跳过原因只影响那一段。"""
    frames = []
    for index, comp in enumerate(comps):
        meta = raw_video_meta(event, index)
        try:
            frames.extend(await _frames_for_comp(index, comp, meta, runner, random_fn))
        except FileNotFoundError:
            # 本进程缺 ffmpeg 或 ffprobe，记一次后这条消息不再抽帧
            _mark_tools_missing()
            return []
    return frames

async def _frames_for_comp(
    index: int, comp: object, meta: dict, runner, random_fn
) -> list:
    """一段视频的帧。这一段不能抽就记下原因并返回空列表。"""
    reason = _size_skip_reason(meta) or _duration_skip_reason(meta.get("duration"))
    # 文件过大或原始段时长已超上限，不下载也不抽
    if reason:
        _log_skip(index, reason)
        return []
    path = await _local_path(comp)
    # 协议端没缓存也下载失败，这一段抽不了
    if not path:
        _log_skip(index, "no_file")
        return []
    duration = meta.get("duration")
    # 原始段没写时长时才用 ffprobe 读容器时长
    if not duration:
        duration = probe_duration_seconds(path, runner)
    # 两条路都没读到时长，不敢按时长取点
    if not duration:
        _log_skip(index, "no_duration")
        return []
    reason = _duration_skip_reason(duration)
    # ffprobe 读出来的时长也可能超上限
    if reason:
        _log_skip(index, reason)
        return []
    stamps = pick_timestamps(duration, frame_count_for(duration), random_fn)
    frames = _extract_frames(path, stamps, runner)
    # 一帧都没抽出来（坏视频、全部超时）这一段跳过
    if not frames:
        _log_skip(index, "no_frame")
        return []
    return frames

def _extract_frames(path: str, stamps: list, runner) -> list:
    """按时间点抽帧。单帧超时或抽空只丢这一帧，别的帧继续。"""
    frames = []
    for stamp in stamps:
        data = extract_png(path, stamp, runner)
        # 这一帧没抽出来就看下一个时间点
        if not data:
            continue
        frames.append(data)
    return frames

def _frames_transcript(frames: list, ocr) -> str:
    """帧 OCR 结果换行拼接。认不出字的帧不进转写。"""
    parts = []
    for frame in frames:
        text = ocr_text_from_bytes(frame, ocr)
        # 这一帧没字就看下一帧
        if not text:
            continue
        parts.append(text)
    return "\n".join(parts)

def _video_user(transcript: str) -> str:
    """送给模型的固定格式。第一行写明来源是短视频抽帧，能走到这里说明没检出码。"""
    return (
        "来源: 短视频抽帧\n"
        "可见文字:\n"
        f"{transcript}\n"
        "二维码: 未检出"
    )

def _size_skip_reason(meta: dict) -> str:
    """原始段报的文件大小是否超上限。空串表示可以下载。"""
    size = meta.get("file_size")
    # 超过 20MB 不下载，省带宽和时间
    if size and size > SHORT_VIDEO_MAX_FILE_BYTES:
        return "too_large"
    return ""

def _duration_skip_reason(duration) -> str:
    """时长是否超上限。空串表示可以抽帧，等于 4.0 仍抽。"""
    # 时长还没读出来时不在这里判断
    if duration is None:
        return ""
    # 大于 4.0 秒不抽帧
    if duration > SHORT_VIDEO_MAX_SECONDS:
        return "too_long"
    return ""

async def _local_path(comp: object) -> str:
    """视频段的本地文件路径。http、base64 和本地路径都由组件自己下载。"""
    convert = getattr(comp, "convert_to_file_path", None)
    # 段上没有转换方法就抽不了
    if not callable(convert):
        return ""
    try:
        raw = convert()
        if inspect.isawaitable(raw):
            raw = await raw
    except Exception:  # noqa: BLE001 - 下载失败类型不固定，这一段跳过即可
        return ""
    return str(raw or "")

def _run_tool(argv: list) -> bytes:
    """默认 runner：跑一次 ffprobe 或 ffmpeg，返回标准输出字节。

    命令不在 PATH 时 subprocess 抛 FileNotFoundError，超时抛 TimeoutExpired。
    测试注入 runner 就不跑真命令，本机没装 ffmpeg 也能跑单测。
    """
    done = subprocess.run(
        argv,
        capture_output=True,
        timeout=SHORT_VIDEO_TOOL_TIMEOUT_SECONDS,
        check=False,
    )
    # 退出码非零（坏视频、编解码失败）当这次没有输出
    if done.returncode != 0:
        return b""
    return done.stdout or b""

def _tool_output(run, argv: list) -> bytes:
    """跑一次工具命令取标准输出。缺命令往上抛，超时和其它启动失败给空字节。"""
    try:
        raw = run(argv)
    except FileNotFoundError:
        # 缺 ffprobe 或 ffmpeg 要让业务层记一次工具缺失，不能当成本次没有输出
        raise
    except (subprocess.TimeoutExpired, OSError):
        # 超时或启动失败当这次没结果，不因超时本身处置消息
        return b""
    return bytes(raw or b"")

def _spaced_enough(points: list, gap: float) -> bool:
    """相邻点间隔都不小于 gap 才算排得开。"""
    ordered = sorted(points)
    for index in range(1, len(ordered)):
        # 挨太近就重抽
        if ordered[index] - ordered[index - 1] < gap:
            return False
    return True

def _even_points(duration: float, count: int) -> list:
    """等分兜底点：按帧数取固定比例乘时长。"""
    ratios = SHORT_VIDEO_EVEN_RATIOS.get(count)
    # 帧数没有约定比例就不抽
    if not ratios:
        return []
    return [duration * ratio for ratio in ratios]

def _raw_video_segments(event: object) -> list:
    """原始数组里 type=video 段的 data。没有就空列表。"""
    obj = getattr(event, "message_obj", None)
    # 残缺事件没有消息对象
    if obj is None:
        return []
    segments = _message_list(getattr(obj, "raw_message", None))
    items = []
    for item in segments:
        # 只认 OneBot 数组格式的原始段
        if not isinstance(item, dict):
            continue
        # 转发段、文本段都不是视频
        if str(item.get("type") or "").lower() != _RAW_VIDEO_TYPE:
            continue
        data = item.get("data")
        # 没有 data 就既没有时长也没有文件大小
        if isinstance(data, dict):
            items.append(data)
    return items

def _message_list(raw: object) -> list:
    """原始体上的 message 数组。"""
    getter = getattr(raw, "get", None)
    # aiocqhttp 的 Event 和普通 dict 都有 get
    if callable(getter):
        segments = getter("message")
    else:
        segments = getattr(raw, "message", None) if raw is not None else None
    # 必须是数组才往下走
    if isinstance(segments, list):
        return segments
    return []

def _positive_seconds(value: object) -> float | None:
    """把原始段字段或 ffprobe 输出收成正秒数。读不到、非正数、NaN 都返回 None。"""
    text = _text_of(value)
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        return None
    # 0、负数和 NaN 都不是可用时长
    if not seconds > 0:
        return None
    return seconds

def _positive_int(value: object) -> int | None:
    """把原始段的文件大小收成正整数。读不到或非正数返回 None。"""
    text = _text_of(value)
    try:
        size = int(float(text))
    except (TypeError, ValueError):
        return None
    # 0 和负数当成没报大小
    if size <= 0:
        return None
    return size

def _text_of(value: object) -> str:
    """把 ffprobe 输出或原始段字段收成字符串。"""
    # ffprobe 走管道给的是字节
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore").strip()
    # 空值没有文本
    if value is None:
        return ""
    return str(value).strip()

def _log_skip(index: int, reason: str) -> None:
    """记一段视频的跳过原因，漏检时能看出是哪一步挡下来的。"""
    _log.info("[rules] video segment skip index=%s reason=%s", index, reason)

def _mark_tools_missing() -> None:
    """本进程第一次发现缺抽帧工具时记一次，之后的短视频都直接跳过。"""
    global _tools_missing
    # 已经记过就不再刷日志
    if _tools_missing:
        return
    _tools_missing = True
    _log.warning("[rules] short video skip reason=tool_missing")
