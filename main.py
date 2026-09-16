# 入口层：向 AstrBot 注册群消息监听、关键词管理工具，以及违禁词 WebUI 测试页。
#
# 群员命中关键词、管理员开/关/批量，都由代码直接回复，不经过模型；回复完拦住事件，
# 模型不会再在后面补一句。开、关、批量不走指令过滤器，所以不需要唤醒前缀。
# 违禁词测试只走插件 Pages，不经 QQ，也不撤回、禁言、发飞书。
#
# 匹配用的是 AstrBot 解析出来的纯文本 event.message_str，不是 OneBot 原始
# raw_message。旧机器人比的是 raw_message，带 @ 或图片的消息会带上 CQ 码，
# 这里改为只比文本段，行为和旧机器人不完全一样。
#
# 陷阱：AstrBot 在唤醒检查阶段会把唤醒前缀从 message_str 开头剥掉，
# 所以「卷卷关键词测试」到这里时已经是「关键词测试」。关键词本身不能以
# 唤醒前缀开头，否则永远匹配不到（business/keyword_admin.py 里已经拦下）。
#
# 本层只做「取群号 → 交给业务层 → 把文本返回」，判断与落库都在 business/。

from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from ._shared.group_switch_store import GroupSwitchStore
from .business.admin_command import handle_admin_command
from .business.forbidden_handle import handle_forbidden_message
from .business.forbidden_judge import (
    complete_yes_no,
    plan_forbidden_test,
    test_result_payload,
)
from .business.keyword_admin import add_rule, delete_rule, list_rules, update_rule
from .business.keyword_reply import pick_reply
from .data.keyword_store import KeywordStore
from .entity.constants import DB_FILE_NAME, PLUGIN_NAME


class RulesPlugin(Star):
    """AstrBot 群规插件。这一版只做关键词回复，后续加违禁词、欢迎语等。"""

    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        # 违禁词样本、设定、禁言秒数、飞书 webhook 走插件 WebUI，不进业务表
        self.config = config
        db_path = Path(StarTools.get_data_dir()) / DB_FILE_NAME
        self.keywords = KeywordStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        self._register_forbidden_page()
        logger.info("[rules] 关键词规则已载入内存：%s", db_path)

    def _register_forbidden_page(self) -> None:
        """注册违禁词 WebUI 测试接口。旧 AstrBot 没有这套 API 就跳过。"""
        register = getattr(self.context, "register_web_api", None)
        # 没这个方法说明当前 AstrBot 还不支持插件 Pages
        if not callable(register):
            return
        register(
            f"/{PLUGIN_NAME}/forbidden/test",
            self.page_forbidden_test,
            ["POST"],
            "违禁词测试",
        )

    async def page_forbidden_test(self):
        """WebUI 测试：触发词门槛 + 当前提供商判断。不发 QQ，不处置。"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        # 不是对象就取不出 text
        if not isinstance(payload, dict):
            return error_response("请求体必须是 JSON 对象", status_code=400)
        text = str(payload.get("text") or "")
        plan = plan_forbidden_test(self.config, text)
        # 没到模型这一步，直接把原因回给页面
        if plan.status != "ready":
            return json_response(test_result_payload(plan, "skip"))
        provider = await self._using_provider()
        # 没配对话模型就测不了
        if provider is None:
            return json_response(
                {
                    "status": "fail",
                    "trigger": plan.trigger,
                    "message": "当前没有可用的对话提供商。",
                }
            )
        verdict = await complete_yes_no(provider, plan.system, plan.user)
        return json_response(test_result_payload(plan, verdict))

    async def _using_provider(self):
        """取当前对话提供商。测试页没有群会话，不传 umo。"""
        getter = getattr(self.context, "get_using_provider_async", None)
        # 老版本没有异步接口
        if not callable(getter):
            return None
        try:
            return await getter()
        except Exception:
            # 提供商没配好时测试页报失败，不要把插件打挂
            return None

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群消息：管理命令、违禁词、关键词。前两条命中后都要停 LLM。"""
        group_id = _group_id_of(event)
        # 拿不到群号就不是群消息，交给别的处理器
        if not group_id:
            return
        text = event.message_str
        # 图片、语音这类没有文本的消息没得比，直接跳过
        if not text:
            return
        # 斜杠开头的是别的插件或默认前缀指令，不拿来当关键词或本插件命令
        if text.startswith("/"):
            return
        handled, reply = await handle_admin_command(
            self.context,
            self.keywords,
            self.switches,
            event,
            group_id,
            text,
        )
        # 管理命令无论有没有回包都要停 LLM，避免带前缀时模型再接一句
        if handled:
            # 管理员有文案；群员误发静默
            if reply:
                yield event.plain_result(reply)
            _stop_llm(event)
            return
        handled, reply = await handle_forbidden_message(
            self.config,
            self.switches,
            event,
            group_id,
            text,
            self._using_provider,
        )
        # 模型判定「是」后已经撤回/禁言/飞书，群提醒有文案才发
        if handled:
            # 提醒留空就只处置，不在群里再说话
            if reply:
                yield event.plain_result(reply)
            _stop_llm(event)
            return
        reply = pick_reply(self.keywords, self.switches, group_id, text)
        # 没命中就静默放过，让消息继续走后面的流程
        if not reply:
            return
        yield event.plain_result(reply)
        # 回完拦住后续 LLM，避免模型又接一句
        _stop_llm(event)

    @filter.llm_tool(name="keyword_add")
    async def tool_keyword_add(
        self,
        event: AstrMessageEvent,
        keyword: str,
        reply: str,
    ) -> str:
        """给本群新增一条关键词回复规则。触发条件是群员整条消息与该关键词完全相等。
        只在 AstrBot 管理员明确要求添加关键词时调用。
        对用户的最终回复只要一句结果，不要预告、不要列方案、不要自己补充解释。

        Args:
            keyword(string): 群员要发送的关键词，必须与整条消息完全一致；不能以唤醒前缀开头
            reply(string): 命中后机器人回复的内容
        """
        group_id = _group_id_of(event)
        # 私聊没有群号，规则没有生效的群
        if not group_id:
            return "这个功能只能在群里用。"
        return await add_rule(
            self.context, self.keywords, event, group_id, keyword, reply
        )

    @filter.llm_tool(name="keyword_update")
    async def tool_keyword_update(
        self,
        event: AstrMessageEvent,
        keyword: str,
        reply: str,
    ) -> str:
        """修改本群某条关键词的回复内容。不要凭记忆判断本群有没有这条关键词，一律调用本工具，
        由它来判定：不存在时它会明确说明，不会悄悄变成新增。对用户的最终回复只要一句结果。

        Args:
            keyword(string): 要修改的关键词，必须与整条消息完全一致
            reply(string): 这条关键词新的回复内容
        """
        group_id = _group_id_of(event)
        if not group_id:
            return "这个功能只能在群里用。"
        return await update_rule(
            self.context, self.keywords, event, group_id, keyword, reply
        )

    @filter.llm_tool(name="keyword_delete")
    async def tool_keyword_delete(
        self,
        event: AstrMessageEvent,
        keyword: str,
    ) -> str:
        """删除本群的一条关键词回复规则。对用户的最终回复只要一句结果。

        Args:
            keyword(string): 要删除的关键词，必须与整条消息完全一致
        """
        group_id = _group_id_of(event)
        if not group_id:
            return "这个功能只能在群里用。"
        return await delete_rule(self.keywords, event, group_id, keyword)

    @filter.llm_tool(name="keyword_list")
    async def tool_keyword_list(self, event: AstrMessageEvent) -> str:
        """列出本群现有的关键词回复规则。管理员想知道本群配了什么时才调用。
        把结果如实转达，不要自己改写或补充。
        """
        group_id = _group_id_of(event)
        if not group_id:
            return "这个功能只能在群里用。"
        return list_rules(self.keywords, event, group_id)


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
