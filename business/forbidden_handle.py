# 业务层：群消息要不要走违禁判断、命中后怎么处置。
# 只有群开关打开、命中触发词、模型整句回答「是」才处置。测试页不走这里。

from .._shared.group_switch_store import GroupSwitchStore
from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import FEATURE_FORBIDDEN
from .forbidden_action import apply_hit_actions
from .forbidden_judge import complete_yes_no, plan_forbidden_test
from .qq_role import is_qq_group_staff


async def handle_forbidden_message(
    config: object,
    store: ForbiddenStore,
    switches: GroupSwitchStore,
    event: object,
    group_id: str,
    text: str,
    get_provider,
    poster=None,
) -> tuple[bool, str]:
    """处理一条群消息的违禁判断。handled=True 时入口要停 LLM。

    返回 (是否已处置, 群提醒文案)。没打开、群管、没命中、模型说否或失败，都不处置。
    """
    # 本群没开违禁词，后面的关键词回复还要继续
    if not switches.is_on(group_id, FEATURE_FORBIDDEN):
        return False, ""
    # QQ 群主或管理员默认安全，不送模型也不处置
    if is_qq_group_staff(event):
        return False, ""
    plan = plan_forbidden_test(config, store, text)
    # 空文本、没触发词、没设定，都按正式路径一样不送模型
    if plan.status != "ready":
        return False, ""
    provider = await get_provider()
    verdict = await complete_yes_no(provider, plan.system, plan.user)
    # 只有整句「是」才处置，否和乱答都不动
    if verdict != "yes":
        return False, ""
    remind = await apply_hit_actions(
        event, config, group_id, plan.trigger, plan.user, poster
    )
    return True, remind
