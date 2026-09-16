# 业务层：把 AstrBot 实际的唤醒前缀拼进给管理员看的文案。
#
# 唤醒前缀是部署级配置，默认是 /，也可以被改成任意词。指令必须带上它才会被
# 识别，所以文案里写死 /关键词 到了自定义前缀的部署上就会误导管理员。
# 前缀统一从这里取，需要展示指令的地方都调 format_command。

from ..entity.constants import DEFAULT_WAKE_PREFIX


def prefixes(context: object) -> list[str]:
    """读全局配置里的唤醒前缀。读不到或配空了都给兜底值，不让文案里出现空串。"""
    raw = _raw_prefixes(context)
    if not raw:
        return [DEFAULT_WAKE_PREFIX]
    return [str(item) for item in raw if str(item)]


def format_command(context: object, command: str) -> str:
    """拼出管理员实际要敲的指令，例如「卷卷关键词 关」。"""
    # 配了多个前缀时只示范第一个，全列出来反而啰嗦
    return f"{prefixes(context)[0]}{command}"


def _raw_prefixes(context: object) -> object:
    """从 AstrBot 全局配置里取 wake_prefix。取不到返回 None，由调用方兜底。"""
    getter = getattr(context, "get_config", None)
    # 拿不到配置入口就交给兜底，不在这里猜
    if not callable(getter):
        return None
    try:
        config = getter()
        config_getter = getattr(config, "get", None)
        # 配置对象不像字典也交给兜底
        if not callable(config_getter):
            return None
        return config_getter("wake_prefix")
    except Exception:
        return None
