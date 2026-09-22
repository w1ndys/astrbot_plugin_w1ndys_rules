# 入口层：向 AstrBot 注册群消息监听、关键词/违禁配置工具，以及违禁词测试页。
#
# 群员命中关键词、管理员开/关/批量/欢迎语设查，都由代码直接回复，不经过模型；回复完拦住事件，
# 模型不会再在后面补一句。这些命令不走指令过滤器，所以不需要唤醒前缀。
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

import asyncio
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from ._shared.group_switch_store import GroupSwitchStore
from .business.activity import record_speak
from .business.admin_command import handle_admin_command
from .business.debug_payload import inspect_payload
from .business.blacklist_admin import (
    REJECT_MESSAGE as BLACKLIST_REJECT,
    add_user,
    delete_user,
    list_users,
)
from .business.forbidden_admin import (
    add_item,
    delete_item,
    list_items,
    update_item,
)
from .business.forbidden_handle import handle_forbidden_message
from .business.group_card import handle_group_card
from .business.forbidden_judge import (
    complete_yes_no,
    plan_forbidden_test,
    test_result_payload,
)
from .business.invite_query import show_downline, show_upline
from .business.invite_record import record_join
from .business.keyword_admin import add_rule, delete_rule, list_rules, update_rule
from .business.keyword_reply import pick_reply
from .business.verify_action import (
    mute_user,
    recall_message_id,
    send_verify_prompt,
    unmute_user,
)
from .business.verify_admin import pass_user, reject_user, scan_users
from .business.verify_handle import PASS_REPLY, handle_verify_private
from .business.verify_join import start_pending
from .business.verify_remind import send_due_remind
from .business.verify_leave import drop_pending, is_group_decrease
from .business.verify_unmute import is_admin_unmute
from .business.welcome_send import is_group_increase, pick_welcome
from .data.activity_store import ActivityStore
from .data.blacklist_store import BlacklistStore
from .data.forbidden_store import ForbiddenStore
from .data.invite_store import InviteStore
from .data.keyword_store import KeywordStore
from .data.verify_store import VerifyStore
from .data.welcome_store import WelcomeStore
from .entity.constants import (
    BLACKLIST_GLOBAL_SCOPE,
    BLACKLIST_LIST_LIMIT,
    DB_FILE_NAME,
    PLUGIN_NAME,
    VERIFY_JOIN_MUTE_SECONDS,
    VERIFY_REMIND_TICK_SECONDS,
)


class RulesPlugin(Star):
    """AstrBot 群规插件。关键词、违禁词、欢迎语和入群验证由本插件处理。"""

    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        # 判断准则、样本、禁言秒数、提醒和 webhook 走 WebUI；触发词全局进数据库。
        self.config = config
        db_path = Path(StarTools.get_data_dir()) / DB_FILE_NAME
        self.keywords = KeywordStore(db_path)
        self.forbidden = ForbiddenStore(db_path)
        self.welcome = WelcomeStore(db_path)
        self.verify = VerifyStore(db_path)
        self.invite = InviteStore(db_path)
        self.blacklist = BlacklistStore(db_path)
        self.activity = ActivityStore(db_path)
        self.switches = GroupSwitchStore(db_path)
        # 提醒循环没有真实事件，发群消息要用这里记下的 OneBot。
        self._onebot = None
        self._remind_task = None
        self._start_remind_loop()
        self._register_forbidden_page()
        logger.info("[rules] 群规业务库已载入内存：%s", db_path)

    def _start_remind_loop(self) -> None:
        """在当前事件循环挂一条扫 pending 的任务。没有循环就先不挂。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 测试或过早加载时还没有事件循环，先不挂
            return
        self._remind_task = loop.create_task(self._remind_loop())

    async def _remind_loop(self) -> None:
        """约每 20 秒扫一次到期 pending。热重载时由 terminate 取消。"""
        while True:
            await asyncio.sleep(VERIFY_REMIND_TICK_SECONDS)
            try:
                await self._tick_reminds()
            except asyncio.CancelledError:
                # 热重载要停循环，不能吞掉取消
                raise
            except Exception:  # noqa: BLE001 - 单次扫失败不能把循环打死
                # 这一拍出错，下一拍再扫，避免一人坏数据停掉全部提醒
                continue

    async def _tick_reminds(self, now_ts: int = 0) -> None:
        """扫到期的人，发新码并撤回上一条。没有 bot 就等下次事件再记。"""
        bot = self._onebot
        # 还没见过任何事件，发不了群消息
        if bot is None:
            return
        # 测试可以传入固定时间；线上用当前 unix 秒
        if now_ts <= 0:
            now_ts = int(time.time())
        event = _BotEvent(bot)
        for group_id, user_id in self.verify.list_due(now_ts):
            try:
                await send_due_remind(
                    self.verify, event, group_id, user_id, now_ts
                )
            except Exception:  # noqa: BLE001 - 一个人失败不影响别人
                # 这个人这一拍跳过，其余到期的人继续发
                continue

    def _remember_bot(self, event: object) -> None:
        """把当前事件上的 OneBot 留下来给提醒循环用。"""
        bot = getattr(event, "bot", None)
        # 残缺事件没有 bot，不能覆盖已记下的
        if bot is None:
            return
        self._onebot = bot

    async def terminate(self) -> None:
        """热重载或卸载时取消提醒循环，避免旧任务继续发。"""
        task = self._remind_task
        # 没挂上循环就不用取消
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

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
        plan = plan_forbidden_test(self.config, self.forbidden, text)
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
        except Exception:  # noqa: BLE001 - 提供商插件异常类型不固定，页面只需返回不可用
            # 提供商没配好时测试页报失败，不要把插件打挂
            return None

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群消息：群名片拦截、管理命令、违禁词、关键词。命中后都要停 LLM。"""
        self._remember_bot(event)
        group_id = _group_id_of(event)
        # 拿不到群号就不是群消息，交给别的处理器
        if not group_id:
            return
        text = event.message_str or ""
        handled, reply = await handle_group_card(self.config, event, group_id)
        # 当前群在 WebUI 名单里时，群名片直接违规，没有正文也要拦
        if handled:
            # 提醒留空就只处置，不在群里再说话
            if reply:
                yield event.plain_result(reply)
            _stop_llm(event)
            await self._note_speak(group_id, event)
            return
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
            self.welcome,
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
            await self._note_speak(group_id, event)
            return
        handled, reply = await handle_forbidden_message(
            self.config,
            self.forbidden,
            self.switches,
            event,
            group_id,
            text,
            self._using_provider,
            activity=self.activity,
        )
        # 模型判定「是」后已经撤回/禁言/飞书。待验证的人发广告也要先走这里。
        if handled:
            # 提醒留空就只处置，不在群里再说话
            if reply:
                yield event.plain_result(reply)
            _stop_llm(event)
            await self._note_speak(group_id, event)
            return
        # 入群验证只认私聊交码，群消息不再当交码
        reply = pick_reply(self.keywords, self.switches, group_id, text)
        # 先记下这次发言，再决定要不要回关键词；必须在违禁判断之后，避免第一条就被当成活跃
        await self._note_speak(group_id, event)
        # 没命中就静默放过，让消息继续走后面的流程
        if not reply:
            return
        yield event.plain_result(reply)
        # 回完拦住后续 LLM，避免模型又接一句
        _stop_llm(event)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private_verify(self, event: AstrMessageEvent):
        """私聊交码。不是待验证就放过，让别的插件和模型继续。"""
        self._remember_bot(event)
        text = event.message_str or ""
        handled, reply = await handle_verify_private(
            self.verify, event, _sender_id_of(event), text
        )
        # 这个人没有 pending，不当验证私聊
        if not handled:
            return
        # 失败回不对；成功回已通过。都在私聊，拦 LLM
        if reply:
            yield event.plain_result(reply)
        _stop_llm(event)

    async def _note_speak(self, group_id: str, event: AstrMessageEvent) -> None:
        """把这次有文本的群发言记下来，给 7 天活跃判断用。"""
        user_id = _sender_id_of(event)
        # 读不到 QQ 号就不要写空键
        if not user_id:
            return
        await record_speak(self.activity, group_id, user_id)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_increase(self, event: AstrMessageEvent):
        """群成员增加：欢迎语和验证说明分开发。空通知也要停 LLM。"""
        self._remember_bot(event)
        group_id = _group_id_of(event)
        # 拿不到群号就不是群通知
        if not group_id:
            return
        # 普通群消息、退群、禁言都不走入群文案
        if not is_group_increase(event):
            return
        # 入群通知没有文本，不拦住的话模型可能对空事件乱回
        _stop_llm(event)
        user_id = _sender_id_of(event)
        # 开关开着才写邀请边；拿不到邀请人由业务层决定不记
        await record_join(
            self.invite,
            self.switches,
            event,
            group_id,
            user_id,
            _self_id_of(event),
        )
        welcome = pick_welcome(self.welcome, self.switches, group_id)
        verify = await start_pending(
            self.verify,
            self.switches,
            group_id,
            user_id,
            _self_id_of(event),
        )
        # 欢迎语单独发，通过后不会被撤回
        if welcome:
            yield _join_at_text(event, user_id, welcome)
        # 没开验证就只发欢迎语
        if not verify:
            return
        await mute_user(event, group_id, user_id, VERIFY_JOIN_MUTE_SECONDS)
        mid = await send_verify_prompt(event, user_id, verify)
        # 没拿到消息 ID 也先让人去私聊交码
        if not mid:
            return
        await self.verify.set_prompt_message_id(group_id, user_id, mid)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_decrease(self, event: AstrMessageEvent):
        """群成员减少：有 pending 就删行。空通知也要停 LLM。"""
        group_id = _group_id_of(event)
        # 拿不到群号就不是群通知
        if not group_id:
            return
        # 入群、普通消息、禁言都不走退群清理
        if not is_group_decrease(event):
            return
        # 退群通知没有文本，不拦住的话模型可能对空事件乱回
        _stop_llm(event)
        user_id = _sender_id_of(event)
        prompt_id = self.verify.get_prompt_message_id(group_id, user_id)
        dropped = await drop_pending(self.verify, group_id, user_id)
        # 本来就没有 pending，没有提示可撤
        if not dropped:
            return
        await recall_message_id(event, prompt_id)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_unmute(self, event: AstrMessageEvent):
        """其他管理员解禁：待验证的人视为通过。空通知也要停 LLM。"""
        group_id = _group_id_of(event)
        # 拿不到群号就不是群通知
        if not group_id:
            return
        # 机器人自己解禁、到期、新禁言都不算通过
        if not is_admin_unmute(event, _self_id_of(event)):
            return
        # 解禁通知没有文本，不拦住的话模型可能对空事件乱回
        _stop_llm(event)
        user_id = _sender_id_of(event)
        prompt_id = self.verify.get_prompt_message_id(group_id, user_id)
        dropped = await drop_pending(self.verify, group_id, user_id)
        # 本来就没有 pending，不用在群里说话
        if not dropped:
            return
        await recall_message_id(event, prompt_id)
        yield event.plain_result(PASS_REPLY)

    @filter.llm_tool(name="forbidden_add")
    async def tool_forbidden_add(
        self,
        event: AstrMessageEvent,
        content: str,
    ) -> str:
        """新增一条全局违禁触发词。只在管理员明确要求新增触发词时调用。
        写操作直接执行，不要再向管理员确认。最终回复要如实保留工具返回的内容。
        违禁样本不走这个工具，请让管理员去 WebUI 填写。

        Args:
            content(string): 要新增的完整触发词
        """
        return await _with_group(
            event, lambda _gid: add_item(self.forbidden, event, content)
        )

    @filter.llm_tool(name="forbidden_update")
    async def tool_forbidden_update(
        self,
        event: AstrMessageEvent,
        old_content: str,
        new_content: str,
    ) -> str:
        """修改一条已有的全局违禁触发词，不存在时不会新增。
        写操作直接执行，不要再向管理员确认。最终回复要如实保留修改前后的内容。

        Args:
            old_content(string): 数据库中现有的完整触发词
            new_content(string): 修改后的完整触发词
        """
        return await _with_group(
            event,
            lambda _gid: update_item(
                self.forbidden, event, old_content, new_content
            ),
        )

    @filter.llm_tool(name="forbidden_delete")
    async def tool_forbidden_delete(
        self,
        event: AstrMessageEvent,
        content: str,
    ) -> str:
        """删除一条全局违禁触发词。最终回复只转达工具结果。

        Args:
            content(string): 要删除的完整触发词
        """
        return await _with_group(
            event, lambda _gid: delete_item(self.forbidden, event, content)
        )

    @filter.llm_tool(name="forbidden_list")
    async def tool_forbidden_list(self, event: AstrMessageEvent) -> str:
        """列出全局违禁触发词。结果必须如实转达。"""
        return await _with_group(
            event, lambda _gid: list_items(self.forbidden, event)
        )

    @filter.llm_tool(name="blacklist_add")
    async def tool_blacklist_add(
        self, event: AstrMessageEvent, user_id: str
    ) -> str:
        """把一个人加入本群黑名单。只在管理员明确要求拉黑时调用。不踢人。
        写操作直接执行。最终回复如实转达工具结果。

        Args:
            user_id(string): 要拉黑的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: add_user(self.blacklist, event, group_id, user_id),
        )

    @filter.llm_tool(name="blacklist_delete")
    async def tool_blacklist_delete(
        self, event: AstrMessageEvent, user_id: str
    ) -> str:
        """从本群黑名单移除一个人。不踢人，也不改群员身份。

        Args:
            user_id(string): 要移除的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: delete_user(
                self.blacklist, event, group_id, user_id
            ),
        )

    @filter.llm_tool(name="blacklist_list")
    async def tool_blacklist_list(self, event: AstrMessageEvent) -> str:
        """列出本群黑名单。超过 30 人会发合并转发。结果必须如实转达。"""
        return await _with_group(
            event,
            lambda group_id: _reply_blacklist(event, self.blacklist, group_id),
        )

    @filter.llm_tool(name="global_blacklist_add")
    async def tool_global_blacklist_add(
        self, event: AstrMessageEvent, user_id: str
    ) -> str:
        """把一个人加入全局黑名单。只在管理员明确要求全局拉黑时调用。不踢人。

        Args:
            user_id(string): 要拉黑的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda _gid: add_user(
                self.blacklist, event, BLACKLIST_GLOBAL_SCOPE, user_id
            ),
        )

    @filter.llm_tool(name="global_blacklist_delete")
    async def tool_global_blacklist_delete(
        self, event: AstrMessageEvent, user_id: str
    ) -> str:
        """从全局黑名单移除一个人。只删全局名单，不改各群名单。

        Args:
            user_id(string): 要移除的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda _gid: delete_user(
                self.blacklist, event, BLACKLIST_GLOBAL_SCOPE, user_id
            ),
        )

    @filter.llm_tool(name="global_blacklist_list")
    async def tool_global_blacklist_list(self, event: AstrMessageEvent) -> str:
        """列出全局黑名单。超过 30 人会发合并转发。结果必须如实转达。"""
        return await _with_group(
            event,
            lambda _gid: _reply_blacklist(
                event, self.blacklist, BLACKLIST_GLOBAL_SCOPE
            ),
        )

    @filter.llm_tool(name="verify_pass")
    async def tool_verify_pass(self, event: AstrMessageEvent, user_id: str) -> str:
        """通过本群某个人的入群验证并解禁。只在管理员明确要求通过时调用。不踢人。
        写操作直接执行。最终回复如实转达工具结果。

        Args:
            user_id(string): 要通过的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: _verify_pass(self.verify, event, group_id, user_id),
        )

    @filter.llm_tool(name="verify_reject")
    async def tool_verify_reject(self, event: AstrMessageEvent, user_id: str) -> str:
        """关掉本群某个人的入群验证。只关 pending，不踢人。
        写操作直接执行。最终回复如实转达工具结果。

        Args:
            user_id(string): 要拒绝的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: _verify_reject(self.verify, event, group_id, user_id),
        )

    @filter.llm_tool(name="verify_scan")
    async def tool_verify_scan(self, event: AstrMessageEvent) -> str:
        """扫描本群待验证的人，并在群里 @ 提醒。结果必须如实转达。不踢人。"""
        return await _with_group(
            event,
            lambda group_id: _verify_scan(self.verify, event, group_id),
        )

    @filter.llm_tool(name="invite_upline")
    async def tool_invite_upline(self, event: AstrMessageEvent, user_id: str) -> str:
        """查询本群某个人的上线链，从他往上追到没有邀请记录为止。结果必须如实转达。

        Args:
            user_id(string): 要查的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: show_upline(self.invite, event, group_id, user_id),
        )

    @filter.llm_tool(name="invite_downline")
    async def tool_invite_downline(self, event: AstrMessageEvent, user_id: str) -> str:
        """查询本群某个人的整条下线，含间接邀请。结果必须如实转达。

        Args:
            user_id(string): 要查的 QQ 号，只填数字
        """
        return await _with_group(
            event,
            lambda group_id: show_downline(self.invite, event, group_id, user_id),
        )

    @filter.llm_tool(name="inspect_message_payload")
    async def tool_inspect_message_payload(
        self,
        event: AstrMessageEvent,
        message_id: str = "",
        sender: str = "",
        keyword: str = "",
    ) -> str:
        """查看指定群消息的原始 OneBot payload，管理员 debug 用。
        引用了某条消息就看那条。
        没引用时去拉群历史：可按发送人（QQ 号或昵称）或消息里的字来找，例如「刚才张三发的那条」。
        最近一页找不到就继续往前翻。没说是谁、也没给关键词时，看上一条。
        只在管理员明确要求查看原始消息、卡片或 payload 时调用。
        工具会把全文私聊发给管理员。最终回复不要把 JSON 贴到群里，只转达工具返回的那一句。

        Args:
            message_id(string): 可选。引用消息时可留空。只填数字消息 ID
            sender(string): 可选。刚才谁发的，QQ 号或群名片/昵称
            keyword(string): 可选。消息或卡片里包含的字
        """
        return await _with_group(
            event,
            lambda group_id: inspect_payload(
                event, group_id, message_id, sender, keyword
            ),
        )

    @filter.llm_tool(name="keyword_add")
    async def tool_keyword_add(
        self,
        event: AstrMessageEvent,
        keyword: str,
        reply: str,
    ) -> str:
        """给本群新增一条关键词回复规则。触发条件是群员整条消息与该关键词完全相等。
        只在机器人的管理员明确要求添加关键词时调用
        对用户的最终回复只要一句结果，不要预告、不要列方案、不要自己补充解释。

        Args:
            keyword(string): 群员要发送的关键词，必须与整条消息完全一致；不能以唤醒前缀开头
            reply(string): 命中后机器人回复的内容
        """
        return await _with_group(
            event,
            lambda group_id: add_rule(
                self.context, self.keywords, event, group_id, keyword, reply
            ),
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
        return await _with_group(
            event,
            lambda group_id: update_rule(
                self.context, self.keywords, event, group_id, keyword, reply
            ),
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
        return await _with_group(
            event,
            lambda group_id: delete_rule(
                self.keywords, event, group_id, keyword
            ),
        )

    @filter.llm_tool(name="keyword_list")
    async def tool_keyword_list(self, event: AstrMessageEvent) -> str:
        """列出本群现有的关键词回复规则。管理员想知道本群配了什么时才调用。
        把结果如实转达，不要自己改写或补充。
        """
        return await _with_group(
            event, lambda group_id: list_rules(self.keywords, event, group_id)
        )


class _BotEvent:
    """提醒循环没有真实 AstrBot 事件，只借用记下的 OneBot。"""

    def __init__(self, bot: object) -> None:
        self.bot = bot


ONLY_IN_GROUP = "这个功能只能在群里用。"


async def _verify_pass(
    store: VerifyStore, event: object, group_id: str, user_id: str
) -> str:
    """管理员通过后解禁、撤回提示、群里 @。没通过就不调 OneBot。"""
    clean = user_id.strip()
    prompt_id = ""
    # 号码合法才去取提示 ID，乱码交给 pass_user 回报
    if clean.isdigit():
        prompt_id = store.get_prompt_message_id(group_id, clean)
    message, unmute = await pass_user(store, event, group_id, user_id)
    # 没删到 pending 不解禁，避免解错人
    if unmute:
        await unmute_user(event, group_id, unmute)
        await recall_message_id(event, prompt_id)
        await send_verify_prompt(event, unmute, PASS_REPLY)
    return message


async def _verify_reject(
    store: VerifyStore, event: object, group_id: str, user_id: str
) -> str:
    """管理员拒绝后撤回入群提示。没删到 pending 不调 OneBot。"""
    clean = user_id.strip()
    prompt_id = ""
    # 号码合法才去取提示 ID，乱码交给 reject_user 回报
    if clean.isdigit():
        prompt_id = store.get_prompt_message_id(group_id, clean)
    message, dropped = await reject_user(store, event, group_id, user_id)
    # 没删到 pending 不撤回，避免撤错消息
    if dropped:
        await recall_message_id(event, prompt_id)
    return message


async def _verify_scan(store: VerifyStore, event: object, group_id: str) -> str:
    """列出本群 pending，有人就在群里 @。"""
    text, ids = scan_users(store, event, group_id)
    # 没人、非管理员都不发 @
    if ids:
        await _send_verify_mentions(event, ids)
    return text


async def _send_verify_mentions(event: object, user_ids: list[str]) -> None:
    """在群里 @ 待验证的人。没有 send 就跳过。"""
    sender = getattr(event, "send", None)
    # 测试桩或残缺事件发不出去
    if not callable(sender):
        return
    from astrbot.api.message_components import At, Plain

    chain: list = []
    for uid in user_ids:
        chain.append(At(qq=uid))
    chain.append(Plain("\n请尽快私聊我发送包含验证码的消息。"))
    await sender(event.chain_result(chain))


def _join_at_text(event: object, user_id: str, text: str):
    """入群欢迎语用 @ 开头。没有 QQ 就只发正文。"""
    # 有入群 QQ 号就先 @，和旧 GroupWelcome 一样
    if user_id:
        from astrbot.api.message_components import At, Plain

        return event.chain_result([At(qq=user_id), Plain("\n" + text)])
    return event.plain_result(text)


async def _with_group(event: object, handler) -> str:
    """配置类工具只能在群里用。handler 拿群号，可以同步或异步。"""
    group_id = _group_id_of(event)
    # 私聊没有群号，规则没有生效的群
    if not group_id:
        return ONLY_IN_GROUP
    result = handler(group_id)
    # 查询类工具直接返回字符串，写操作返回协程
    if isinstance(result, str):
        return result
    return await result


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


def _sender_id_of(event: object) -> str:
    """从事件里取发言人/入群人 QQ 号。没有就空串。"""
    getter = getattr(event, "get_sender_id", None)
    # 残缺事件没有这个方法
    if getter is None:
        return ""
    value = getter()
    # 空值统一成空串
    if not value:
        return ""
    return str(value)


def _self_id_of(event: object) -> str:
    """机器人自己的 QQ。没有就空串，入群验证无法跳过自己。"""
    getter = getattr(event, "get_self_id", None)
    # 残缺事件没有这个方法
    if getter is None:
        return ""
    value = getter()
    # 空值统一成空串
    if not value:
        return ""
    return str(value)


async def _reply_blacklist(event: object, store: BlacklistStore, group_id: str) -> str:
    """名单不超过上限时把全文交给模型；超过就发合并转发。"""
    text = list_users(store, event, group_id)
    # 非管理员只回报拒绝，不查人数也不发消息
    if text == BLACKLIST_REJECT:
        return text
    ids = store.list_user_ids(group_id)
    # 空名单和短名单都让模型原样转述
    if len(ids) <= BLACKLIST_LIST_LIMIT:
        return text
    await _send_forward_text(event, text)
    # 全局名单和本群名单用同一句式
    if group_id == BLACKLIST_GLOBAL_SCOPE:
        name = "全局黑名单"
    else:
        name = "本群黑名单"
    return f"已用合并消息发出{name}，共 {len(ids)} 人。"


async def _send_forward_text(event: object, text: str) -> None:
    """把整份名单塞进一条合并转发。"""
    from astrbot.api.message_components import Node, Plain

    getter = getattr(event, "get_self_id", None)
    # 读不到机器人 QQ 时用 0，合并转发仍能发出
    if getter is None:
        uin = "0"
    else:
        uin = str(getter() or "0")
    node = Node(uin=uin, name=PLUGIN_NAME, content=[Plain(text)])
    await event.send(event.chain_result([node]))


def _stop_llm(event: object) -> None:
    """拦住后续 LLM。要回的内容已经回过了，不要让模型再跟一句。"""
    stop = getattr(event, "stop_event", None)
    # 老版本 AstrBot 没有 stop_event，拦不住时就只发自己的回复
    if callable(stop):
        stop()
