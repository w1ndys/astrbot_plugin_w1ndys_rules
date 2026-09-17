# 业务层：管理员用代码命令设置、查看本群欢迎语文案。
#
# 开、关走 switch_command；本文件只动文案。入群发送不在这里。
# 群号由入口层传入，本层不碰 AstrBot 的平台 API。

from ..data.welcome_store import WelcomeStore
from ..entity.constants import CMD_WELCOME_SET, WELCOME_MAX_LEN
from .auth import is_admin

# 非管理员统一回这句话。群消息路径会先静默，这里给直接调用兜底。
REJECT_MESSAGE = "只有机器人的管理员能管理本群的欢迎语"


def usage_text() -> str:
    """没贴文案时的用法。欢迎语命令不带唤醒前缀。"""
    return (
        f"用法：在「{CMD_WELCOME_SET}」后面写文案，同一行或换行都可以。\n"
        "示例：\n"
        f"{CMD_WELCOME_SET} 欢迎入群~"
    )


def strip_set_header(text: str) -> str:
    """去掉「欢迎语 设置」命令头，留下要保存的文案。"""
    payload = text.replace("\ufeff", "")
    lines = payload.splitlines()
    # 空消息没有文案
    if not lines:
        return ""
    first = lines[0].strip()
    rest = lines[1:]
    extra = ""
    # 第一行只是命令，文案在后面的换行里
    if first == CMD_WELCOME_SET:
        extra = ""
    # 命令和文案写在同一行，中间必须是空格或 Tab
    elif first.startswith(CMD_WELCOME_SET) and first[len(CMD_WELCOME_SET)] in " \t":
        extra = first[len(CMD_WELCOME_SET) :].strip()
    else:
        # 第一行不是命令头，整段都当文案
        return payload.strip()
    # 同一行里命令后面还带着正文，要拼回后面的行
    if extra:
        return "\n".join([extra, *rest]).strip()
    return "\n".join(rest).strip()


def show_welcome(store: WelcomeStore, event: object, group_id: str) -> str:
    """查出本群已保存的欢迎语。没设过就说明用法。"""
    # 非管理员不能看本群文案
    if not is_admin(event):
        return REJECT_MESSAGE
    content = store.get_content(group_id)
    # 没写过文案，入群发送时才会用默认句，这里不假装已经设了
    if not content:
        return f"本群还没有设置欢迎语。{usage_text()}"
    return f"本群欢迎语：\n{content}"


async def set_welcome(
    store: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> str:
    """写入或覆盖本群欢迎语。空文案不落库。"""
    # 非管理员不能改文案
    if not is_admin(event):
        return REJECT_MESSAGE
    content = strip_set_header(text)
    # 只发了命令没贴文案，告诉用法，不要把空串写进库
    if not content:
        return usage_text()
    # 超长文案不落库，避免误贴整篇文章
    if len(content) > WELCOME_MAX_LEN:
        return f"欢迎语太长了，最多 {WELCOME_MAX_LEN} 个字"
    await store.set_content(group_id, content)
    return f"已设置本群欢迎语：\n{content}"
