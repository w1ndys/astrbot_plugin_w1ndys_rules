# 业务层：近 7 天本群发过言就算活跃。不查 OneBot，不踢人。

from ..data.activity_store import ActivityStore


def is_recently_active(store: ActivityStore, group_id: str, user_id: str) -> bool:
    """近 7 天在本群发过言就算活跃。缺群号、缺人或没记录都不是。"""
    # 没有群号就谈不上「本群」
    if not group_id:
        return False
    # 没有 QQ 号无法对上人，继续送模型
    if not user_id:
        return False
    return store.is_within_window(group_id, user_id)


async def record_speak(store: ActivityStore, group_id: str, user_id: str) -> None:
    """记下这个人在本群刚发过言。缺群号或缺人就不写。"""
    # 没有群号写进去也对不上后续查询
    if not group_id:
        return
    # 没有 QQ 号就不要占一行空键
    if not user_id:
        return
    await store.touch(group_id, user_id)
