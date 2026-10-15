# 入口层环境提醒：加载时缺依赖就私聊管理员；装齐、没管理员、平台没起来都不发。

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def install_astrbot_stubs() -> None:
    """安装最小 AstrBot 模块，让单元测试可以导入插件入口。"""
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")
    components = types.ModuleType("astrbot.api.message_components")

    class IdentityFilter:
        """把 AstrBot 装饰器替换成不改变函数的测试装饰器。"""

        class EventMessageType:
            GROUP_MESSAGE = "group"
            PRIVATE_MESSAGE = "private"

        def event_message_type(self, _message_type):
            """返回原函数。"""
            return lambda function: function

        def llm_tool(self, **_kwargs):
            """返回原函数。"""
            return lambda function: function

    class Star:
        """测试用插件基类。"""

    class StarTools:
        """测试不会调用真实数据目录。"""

        @staticmethod
        def get_data_dir() -> str:
            """返回当前目录作为兜底。"""
            return "."

    class Logger:
        """忽略入口层日志。"""

        def info(self, *_args, **_kwargs) -> None:
            """测试不输出日志。"""
            return

        def warning(self, *_args, **_kwargs) -> None:
            """测试不输出日志。"""
            return

    class Plain:
        def __init__(self, text, **_kwargs) -> None:
            self.text = text

    event.AstrMessageEvent = object
    event.filter = IdentityFilter()
    star.Context = object
    star.Star = Star
    star.StarTools = StarTools
    api.logger = Logger()
    components.Plain = Plain
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.message_components"] = components


install_astrbot_stubs()

import astrbot_plugin_w1ndys_rules.main as plugin_main
from astrbot_plugin_w1ndys_rules.main import RulesPlugin


class FakeApi:
    """记下 OneBot 动作调用。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.error = error

    async def call_action(self, action: str, **kwargs):
        """记一笔；要模拟失败就在记完之后抛出去。"""
        self.calls.append((action, kwargs))
        if self.error is not None:
            raise self.error
        return {}


class FakeBot:
    """只带 api.call_action 的客户端，和入口层认的同一套。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.api = FakeApi(error)


class FakeAdapter:
    """模仿 aiocqhttp：get_client 交出客户端。"""

    def __init__(self, bot: object) -> None:
        self._bot = bot

    def get_client(self) -> object:
        """和官方适配器一样交客户端。"""
        return self._bot


class FakePlatforms:
    """context.platform_manager 只需要 platform_insts 列表。"""

    def __init__(self, insts: list) -> None:
        self.platform_insts = insts


class FakeContext:
    """入口层要用的两样：全局配置和已加载的平台。"""

    def __init__(self, config: dict, insts: list | None = None) -> None:
        self._config = config
        self.platform_manager = FakePlatforms(insts or [])

    def get_config(self) -> dict:
        """返回 AstrBot 全局配置。"""
        return self._config


class EnvNoticeTest(unittest.IsolatedAsyncioTestCase):
    # 加载时体检并私聊管理员

    def setUp(self) -> None:
        # 体检结果由测试决定，不受本机装没装影响
        self._saved_missing = plugin_main.missing_packages
        self._saved_wait = plugin_main.ENV_NOTICE_WAIT_SECONDS
        self._saved_tries = plugin_main.ENV_NOTICE_MAX_TRIES

        def fake_missing() -> list:
            """固定缺 qreader。"""
            return [("qreader", "qreader")]

        plugin_main.missing_packages = fake_missing
        plugin_main.ENV_NOTICE_WAIT_SECONDS = 0
        self.bot = FakeBot()
        self.plugin = RulesPlugin.__new__(RulesPlugin)
        self.plugin._onebot = None
        self.plugin._remind_task = None
        self.plugin._env_notice_task = None

    def tearDown(self) -> None:
        plugin_main.missing_packages = self._saved_missing
        plugin_main.ENV_NOTICE_WAIT_SECONDS = self._saved_wait
        plugin_main.ENV_NOTICE_MAX_TRIES = self._saved_tries

    def use_context(self, admins: list, insts: list | None = None) -> None:
        """给插件挂一个带配置和平台的假 context。"""
        self.plugin.context = FakeContext({"admins_id": admins}, insts)

    async def test_notifies_each_admin(self) -> None:
        # 缺依赖时每位管理员各收一条私聊，号码对得上
        self.use_context(["10001", "10002"], [FakeAdapter(self.bot)])
        await self.plugin.initialize()
        await self.plugin._env_notice_task
        calls = self.bot.api.calls
        self.assertEqual([item[0] for item in calls], ["send_private_msg"] * 2)
        self.assertEqual([item[1]["user_id"] for item in calls], [10001, 10002])
        self.assertIn("qreader", calls[0][1]["message"])

    async def test_skips_when_env_complete(self) -> None:
        # 装齐了就不打扰管理员
        def fake_missing() -> list:
            """一个都不缺。"""
            return []

        plugin_main.missing_packages = fake_missing
        self.use_context(["10001"], [FakeAdapter(self.bot)])
        await self.plugin.initialize()
        self.assertIsNone(self.plugin._env_notice_task)
        self.assertEqual(self.bot.api.calls, [])

    async def test_placeholder_admin_is_skipped(self) -> None:
        # 默认占位（astrbot）不是 QQ 号，只留日志不发
        self.use_context(["astrbot"], [FakeAdapter(self.bot)])
        await self.plugin.initialize()
        self.assertIsNone(self.plugin._env_notice_task)
        self.assertEqual(self.bot.api.calls, [])

    async def test_gives_up_without_platform(self) -> None:
        # 平台一直没起来：不抛异常，也不发消息
        plugin_main.ENV_NOTICE_MAX_TRIES = 1
        self.use_context(["10001"], [])
        await self.plugin.initialize()
        await self.plugin._env_notice_task
        self.assertEqual(self.bot.api.calls, [])

    async def test_send_failure_is_swallowed(self) -> None:
        # 协议端抛错只当发失败，不能把插件打挂
        bot = FakeBot(RuntimeError("boom"))
        self.use_context(["10001"], [FakeAdapter(bot)])
        await self.plugin.initialize()
        await self.plugin._env_notice_task
        self.assertEqual(len(bot.api.calls), 1)

    async def test_terminate_cancels_pending_notice(self) -> None:
        # 热重载要停掉还在等的提醒任务
        plugin_main.ENV_NOTICE_WAIT_SECONDS = 30
        self.use_context(["10001"], [])
        await self.plugin.initialize()
        await self.plugin.terminate()
        self.assertTrue(self.plugin._env_notice_task.cancelled())


class AdminIdsTest(unittest.TestCase):
    # 管理员 QQ 读取口径

    def test_reads_digit_ids_only(self) -> None:
        # 非数字（默认占位）和空白都不算
        context = FakeContext({"admins_id": ["10001", "astrbot", " 10002 "]}, [])
        self.assertEqual(plugin_main._admin_ids(context), ["10001", "10002"])

    def test_single_string_becomes_list(self) -> None:
        # 配置里只写一个字符串也认
        context = FakeContext({"admins_id": "10001"}, [])
        self.assertEqual(plugin_main._admin_ids(context), ["10001"])

    def test_missing_config_is_empty(self) -> None:
        # 老版本没有 get_config，或者配置里没这一项，都当没人可发
        self.assertEqual(plugin_main._admin_ids(object()), [])
        self.assertEqual(plugin_main._admin_ids(FakeContext({}, [])), [])

    def test_config_error_is_empty(self) -> None:
        # 读配置抛错当成没配，不能把加载打挂
        class Boom:
            """get_config 直接抛错的替身。"""

            def get_config(self):
                """模拟读配置失败。"""
                raise RuntimeError("bad")

        self.assertEqual(plugin_main._admin_ids(Boom()), [])
