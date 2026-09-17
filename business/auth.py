# 业务层：谁能改本群的配置。
#
# 关键词规则和群开关都只认 AstrBot 后台里配置的管理员：群员既不能把机器人
# 点开，也不能自己往库里写规则。判定收在这里，两个功能共用一份。


def is_admin(event: object) -> bool:
    """当前发言人是不是 AstrBot 后台里配置的管理员。"""
    checker = getattr(event, "is_admin", None)
    # 没有这个方法就当不是管理员，宁可拒绝也不要误放行
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception:  # noqa: BLE001 - 第三方事件实现可能抛出任意异常，权限必须默认拒绝
        return False
