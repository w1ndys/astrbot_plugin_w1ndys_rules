# 业务层：群主、群管理员或 AstrBot 管理员用代码命令设置、查看本群欢迎语。
#
# 开、关名单仍走 WebUI；本文件只动本群独立文案。入群发送不在这里。
# 群号由入口层传入，本层不碰 AstrBot 的平台 API。
# 无权的人误发要静默，回拒绝语会刷屏。

from ..data.welcome_store import WelcomeStore
from ..entity.constants import (
    CMD_WELCOME_SET,
    DEFAULT_WELCOME_TEXT,
    WELCOME_MAX_LEN,
)
from .auth import is_admin
from .qq_role import is_qq_group_staff


def can_edit_welcome(event: object) -> bool:
    """本群群主、群管理员或 AstrBot 管理员才能改欢迎语。"""
    # AstrBot 后台管理员可以跨群改文案
    if is_admin(event):
        return True
    # 本群群主或管理员也能改本群
    return is_qq_group_staff(event)


def usage_text() -> str:
    """没单独设置时的说明。欢迎语命令不带唤醒前缀。"""
    return (
        f"用法：在「{CMD_WELCOME_SET}」后面写文案，同一行或换行都可以。"
        "只发命令不写文案则关闭本群欢迎语。" + "\n"
        "示例：" + "\n" + f"{CMD_WELCOME_SET} 欢迎入群~"
    )


def strip_set_header(text: str) -> str:
    """去掉「欢迎语 设置」命令头，留下要保存的文案。"""
    payload = text.replace("\ufeff", "")
    lines = payload.splitlines()
    # 空消息没有文案，按置空关闭
    if not lines:
        return ""
    first = lines[0].strip()
    rest = lines[1:]
    extra = ""
    # 第一行只是命令，文案在后面的换行里
    if first == CMD_WELCOME_SET:
        extra = ""
    # 命令和文案写在同一行，中间必须是空格或 Tab
    elif (
        first.startswith(CMD_WELCOME_SET)
        and len(first) > len(CMD_WELCOME_SET)
        and first[len(CMD_WELCOME_SET)] in (" ", "\t")
    ):
        extra = first[len(CMD_WELCOME_SET) :].strip()
    else:
        # 第一行不是命令头，整段都当文案
        return payload.strip()
    # 同一行里命令后面还带着正文，要拼回后面的行
    if extra:
        return "\n".join([extra, *rest]).strip()
    return "\n".join(rest).strip()


def show_welcome(store: WelcomeStore, event: object, group_id: str) -> str:
    """查出本群独立欢迎语。没设过说明走全局；空串说明已关闭。"""
    # 无权查看时静默，避免群员误发刷屏
    if not can_edit_welcome(event):
        return ""
    content = store.get_content(group_id)
    # 没写过独立配置，入群时用全局或默认句
    if content is None:
        return (
            "本群还没有单独设置欢迎语。"
            f"入群时用全局文案，没填则发「{DEFAULT_WELCOME_TEXT}」。"
            f"{usage_text()}"
        )
    # 独立配置为空：本群关闭，压过开启名单
    if not content:
        return "本群欢迎语已关闭。独立配置为空，即使在开启名单里也不发。"
    return "本群欢迎语：" + "\n" + content


async def set_welcome(
    store: WelcomeStore,
    event: object,
    group_id: str,
    text: str,
) -> str:
    """写入或覆盖本群欢迎语。空文案落库，表示本群关闭。"""
    # 无权改时静默
    if not can_edit_welcome(event):
        return ""
    content = strip_set_header(text)
    # 超长文案不落库，避免误贴整篇文章
    if len(content) > WELCOME_MAX_LEN:
        return f"欢迎语太长了，最多 {WELCOME_MAX_LEN} 个字"
    await store.set_content(group_id, content)
    # 空串关闭本群欢迎，优先于开启名单
    if not content:
        return "已关闭本群欢迎语。独立配置为空，即使在开启名单里也不发。"
    return "已设置本群欢迎语：" + "\n" + content
