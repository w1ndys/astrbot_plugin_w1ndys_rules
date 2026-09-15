# 入口层：向 AstrBot 注册群消息监听和 /kr 群开关命令。
#
# 群员命中关键词由代码直接回复，不经过模型；回复完拦住事件，
# 模型不会再在关键词回复后面补一句。
#
# 匹配用的是 AstrBot 解析出来的纯文本 event.message_str，不是 OneBot 原始
# raw_message。旧机器人比的是 raw_message，带 @ 或图片的消息会带上 CQ 码，
# 这里改为只比文本段，行为和旧机器人不完全一样。

from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from ._shared.group_switch_store import GroupSwitchStore
from .business.keyword_reply import pick_reply
from .business.switch_command import run_switch_command
from .data.keyword_store import KeywordStore
from .entity.constants import DB_FILE_NAME


class RulesPlugin(Star):
    """AstrBot 群规插件。这一版只做关键词回复，后续加违禁词、欢迎语等。"""

    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        db_path = Path(StarTools.get_data_dir()) / DB_FILE_NAME
        self.keywords = KeywordStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        logger.info("[rules] 关键词规则已载入内存：%s", db_path)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群员发消息时，命中关键词就用代码回一句，不进模型。"""
        group_id = _group_id_of(event)
        # 拿不到群号就不是群消息，交给别的处理器
        if not group_id:
            return
        text = event.message_str
        # 图片、语音这类没有文本的消息没得比，直接跳过
        if not text:
            return
        # 斜杠开头的是 AstrBot 指令（唤醒前缀默认是 /），
        # 交给指令处理器，不拿来当关键词匹配
        if text.startswith("/"):
            return
        reply = pick_reply(self.keywords, self.switches, group_id, text)
        # 没命中就静默放过，让消息继续走后面的流程
        if not reply:
            return
        yield event.plain_result(reply)
        # 回完拦住后续 LLM，避免模型又接一句
        _stop_llm(event)

    @filter.command_group("kr")
    def kr(self):
        """关键词回复：/kr 开、/kr 关。指令组本身不做事，只用来挂子指令。"""

    @kr.command("开")
    async def kr_on(self, event: AstrMessageEvent):
        """打开本群的关键词回复。只有 AstrBot 管理员能执行。"""
        group_id = _group_id_of(event)
        # 私聊没有群号，群开关没有对象群
        if not group_id:
            yield event.plain_result("这个命令要在群里用。")
            return
        text = await run_switch_command(self.switches, event, group_id, True)
        yield event.plain_result(text)
        # 指令自己回了就够了，不要再让模型接话
        _stop_llm(event)

    @kr.command("关")
    async def kr_off(self, event: AstrMessageEvent):
        """关闭本群的关键词回复。只有 AstrBot 管理员能执行。"""
        group_id = _group_id_of(event)
        # 私聊没有群号，群开关没有对象群
        if not group_id:
            yield event.plain_result("这个命令要在群里用。")
            return
        text = await run_switch_command(self.switches, event, group_id, False)
        yield event.plain_result(text)
        # 指令自己回了就够了，不要再让模型接话
        _stop_llm(event)


def _group_id_of(event: object) -> str:
    """从事件里取群号。私聊没有群号，返回空串。"""
    getter = getattr(event, "get_group_id", None)
    # 取不到就按私聊处理，调用方会拒绝
    if getter is None:
        return ""
    value = getter()
    # 空值统一成空串，省得调用方再判一次 None
    if not value:
        return ""
    return str(value)


def _stop_llm(event: object) -> None:
    """拦住后续 LLM。要回的内容已经回过了，不要让模型再跟一句。"""
    stop = getattr(event, "stop_event", None)
    # 老版本 AstrBot 没有 stop_event，拦不住时就只发自己的回复
    if callable(stop):
        stop()
