# 业务层：管理员用自然语言增删改查全局违禁触发词。样本走 WebUI，这里不管。

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import (
    FORBIDDEN_GLOBAL_SCOPE,
    FORBIDDEN_ITEM_MAX_LEN,
    FORBIDDEN_KIND_TRIGGER,
    FORBIDDEN_LIST_LIMIT,
)
from .auth import is_admin

REJECT_MESSAGE = "只有 AstrBot 管理员能管理违禁触发词。"
TRIGGER_LABEL = "违禁触发词"


def clean_content(content: str) -> tuple[str, str]:
    """去掉首尾空白并校验单条触发词长度。"""
    text = content.strip()
    # 空内容无法参与包含匹配。
    if not text:
        return "", "内容不能为空。"
    # 限制单条长度，避免误粘贴整篇文本占用数据库和快照。
    if len(text) > FORBIDDEN_ITEM_MAX_LEN:
        return "", f"内容太长了，最多 {FORBIDDEN_ITEM_MAX_LEN} 个字。"
    return text, ""


async def add_item(store: ForbiddenStore, event: object, content: str) -> str:
    """新增一条全局违禁触发词。"""
    # 权限在业务层强制检查，不能依赖模型是否展示工具。
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_content(content)
    # 内容错误时不访问数据库。
    if error:
        return error
    added = await store.add(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, clean)
    # 唯一键冲突不能覆盖已有内容。
    if not added:
        return f"已经存在{TRIGGER_LABEL}「{clean}」，没有重复添加。"
    return f"已添加{TRIGGER_LABEL}「{clean}」。"


async def update_item(
    store: ForbiddenStore,
    event: object,
    old_content: str,
    new_content: str,
) -> str:
    """修改一条已有的全局违禁触发词。"""
    # 权限在业务层强制检查，防止非管理员直接调用工具。
    if not is_admin(event):
        return REJECT_MESSAGE
    old_clean, error = clean_content(old_content)
    # 原内容也必须是合法的查询键。
    if error:
        return error
    new_clean, error = clean_content(new_content)
    # 新内容不合法时保留原数据。
    if error:
        return error
    # 内容没有变化时不写数据库。
    if old_clean == new_clean:
        return f"{TRIGGER_LABEL}本来就是「{new_clean}」，没有改动。"
    result = await store.update(
        FORBIDDEN_GLOBAL_SCOPE,
        FORBIDDEN_KIND_TRIGGER,
        old_clean,
        new_clean,
    )
    return _update_message(result, old_clean, new_clean)


def _update_message(result: str, old: str, new: str) -> str:
    """根据数据层结果生成不会误报成功的修改回报。"""
    # 原内容不存在时不能把修改降级成新增。
    if result == "missing":
        return f"没有{TRIGGER_LABEL}「{old}」，没有修改。"
    # 新内容已存在时保留原来的两条数据。
    if result == "conflict":
        return f"已经存在{TRIGGER_LABEL}「{new}」，没有修改。"
    return f"已将{TRIGGER_LABEL}「{old}」修改为「{new}」。"


async def delete_item(store: ForbiddenStore, event: object, content: str) -> str:
    """删除一条全局违禁触发词。"""
    # 非管理员不能删库。
    if not is_admin(event):
        return REJECT_MESSAGE
    clean, error = clean_content(content)
    # 空内容和超长内容不拿去查询数据库。
    if error:
        return error
    removed = await store.delete(
        FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER, clean
    )
    # 没有删到行时必须如实回报。
    if not removed:
        return f"没有{TRIGGER_LABEL}「{clean}」，没有删除。"
    return f"已删除{TRIGGER_LABEL}「{clean}」。"


def list_items(store: ForbiddenStore, event: object) -> str:
    """列出全局违禁触发词。"""
    # 查询也属于管理能力，非管理员不能读取规则。
    if not is_admin(event):
        return REJECT_MESSAGE
    triggers = store.list_contents(FORBIDDEN_GLOBAL_SCOPE, FORBIDDEN_KIND_TRIGGER)
    # 空列表用一句明确文案结束。
    if not triggers:
        return "还没有违禁触发词。"
    return "\n".join(_format_section("违禁触发词", triggers))


def _format_section(label: str, contents: list[str]) -> list[str]:
    """格式化触发词列表，限制返回数量以避免群里刷屏。"""
    lines = [f"{label}（{len(contents)} 条）："]
    for content in contents[:FORBIDDEN_LIST_LIMIT]:
        lines.append(f"「{content}」")
    # 超出上限时只报告剩余数量。
    if len(contents) > FORBIDDEN_LIST_LIMIT:
        rest = len(contents) - FORBIDDEN_LIST_LIMIT
        lines.append(f"（其余 {rest} 条未显示）")
    return lines
