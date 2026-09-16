# 业务层：读 AstrBot 实际的唤醒前缀。
#
# 唤醒前缀是部署级配置，默认是 /，也可以被改成任意词。AstrBot 在唤醒检查阶段
# 会把前缀从 message_str 开头剥掉，所以关键词不能以前缀开头，否则永远匹配不到。
# 写入关键词时用这里读到的前缀做校验。

from ..entity.constants import DEFAULT_WAKE_PREFIX


def prefixes(context: object) -> list[str]:
    """读全局配置里的唤醒前缀。读不到或配空了都给兜底值，不让文案里出现空串。"""
    raw = _raw_prefixes(context)
    # 配置缺失或全是空串时用兜底，避免校验失效
    if not raw:
        return [DEFAULT_WAKE_PREFIX]
    return [str(item) for item in raw if str(item)]


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
