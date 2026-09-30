# 业务层：WebUI 群号名单决定某个功能在本群开没开。
# 空名单、不是列表、对不上群号都当关。不读旧的 SQLite 开关表。

def feature_on(config: object, key: str, group_id: str) -> bool:
    """本群是否写在这份 WebUI 名单里。没写就关。"""
    # 没有群号对不上名单，不能当开启
    if not group_id:
        return False
    for item in config_group_ids(config, key):
        # 名单里这一项就是本群
        if item == group_id:
            return True
    return False


def config_group_ids(config: object, key: str) -> list:
    """从 WebUI 取出一份群号名单。只认按条添加的列表。"""
    value = _config_raw(config, key)
    # 不是数组就当没配，旧文本框不再拆
    if not isinstance(value, list):
        return []
    return _clean_group_ids(value)


def _config_raw(config: object, key: str):
    """从插件配置取出原值。没有配置返回 None。"""
    # 没挂上 WebUI 配置就当全空
    if config is None:
        return None
    getter = getattr(config, "get", None)
    # 配置对象不像字典也当没有
    if not callable(getter):
        return None
    return getter(key)


def _clean_group_ids(items: list) -> list:
    """去掉空项和首尾空白，得到可比较的群号。"""
    result = []
    for item in items:
        text = str(item).strip()
        # 空项忽略，避免 WebUI 空白行把功能误开
        if not text:
            continue
        result.append(text)
    return result
