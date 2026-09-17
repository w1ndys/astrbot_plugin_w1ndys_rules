# 业务层：管理员用自然语言增删改查本群违禁触发词和违禁样本。

from ..data.forbidden_store import ForbiddenStore
from ..entity.constants import (
    FORBIDDEN_ITEM_MAX_LEN,
    FORBIDDEN_KIND_SAMPLE,
    FORBIDDEN_KIND_TRIGGER,
    FORBIDDEN_LIST_LIMIT,
)
from .auth import is_admin

REJECT_MESSAGE = "只有 AstrBot 管理员能管理本群的违禁配置。"


def kind_details(raw_kind: str) -> tuple[str, str, str]:
    """把工具收到的中文类型转成内部值、展示名和错误文案。"""
    text = raw_kind.strip()
    # 触发词决定群消息是否进入模型判断。
    if text == "触发词":
        return FORBIDDEN_KIND_TRIGGER, "违禁触发词", ""
    # 违禁样本只作为模型的判断参考。
    if text == "违禁样本":
        return FORBIDDEN_KIND_SAMPLE, "违禁样本", ""
    return "", "", "类型只能是「触发词」或「违禁样本」。"


def clean_content(content: str) -> tuple[str, str]:
    """去掉首尾空白并校验单条内容长度。"""
    text = content.strip()
    # 空内容无法参与匹配或给模型提供信息。
    if not text:
        return "", "内容不能为空。"
    # 限制单条长度，避免误粘贴整篇文本占用数据库和上下文。
    if len(text) > FORBIDDEN_ITEM_MAX_LEN:
        return "", f"内容太长了，最多 {FORBIDDEN_ITEM_MAX_LEN} 个字。"
    return text, ""


async def add_item(
    store: ForbiddenStore,
    event: object,
    group_id: str,
    raw_kind: str,
    content: str,
) -> str:
    """给本群新增一条违禁触发词或违禁样本。"""
    # 权限在业务层强制检查，不能依赖模型是否展示工具。
    if not is_admin(event):
        return REJECT_MESSAGE
    kind, label, error = kind_details(raw_kind)
    # 类型错误时不访问数据库。
    if error:
        return error
    clean, error = clean_content(content)
    # 内容错误时不访问数据库。
    if error:
        return error
    added = await store.add(group_id, kind, clean)
    # 唯一键冲突不能覆盖已有内容。
    if not added:
        return f"本群已经存在{label}「{clean}」，没有重复添加。"
    return f"已添加{label}「{clean}」。"


async def update_item(
    store: ForbiddenStore,
    event: object,
    group_id: str,
    raw_kind: str,
    old_content: str,
    new_content: str,
) -> str:
    """修改本群一条已有的违禁触发词或违禁样本。"""
    # 权限在业务层强制检查，防止非管理员直接调用工具。
    if not is_admin(event):
        return REJECT_MESSAGE
    kind, label, error = kind_details(raw_kind)
    # 类型错误时不访问数据库。
    if error:
        return error
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
        return f"{label}本来就是「{new_clean}」，没有改动。"
    result = await store.update(group_id, kind, old_clean, new_clean)
    return _update_message(result, label, old_clean, new_clean)


def _update_message(result: str, label: str, old: str, new: str) -> str:
    """根据数据层结果生成不会误报成功的修改回报。"""
    # 原内容不存在时不能把修改降级成新增。
    if result == "missing":
        return f"本群没有{label}「{old}」，没有修改。"
    # 新内容已存在时保留原来的两条数据。
    if result == "conflict":
        return f"本群已经存在{label}「{new}」，没有修改。"
    return f"已将{label}「{old}」修改为「{new}」。"


async def delete_item(
    store: ForbiddenStore,
    event: object,
    group_id: str,
    raw_kind: str,
    content: str,
) -> str:
    """删除本群一条违禁触发词或违禁样本。"""
    # 非管理员不能删库。
    if not is_admin(event):
        return REJECT_MESSAGE
    kind, label, error = kind_details(raw_kind)
    # 类型错误时不访问数据库。
    if error:
        return error
    clean, error = clean_content(content)
    # 空内容和超长内容不拿去查询数据库。
    if error:
        return error
    removed = await store.delete(group_id, kind, clean)
    # 没有删到行时必须如实回报。
    if not removed:
        return f"本群没有{label}「{clean}」，没有删除。"
    return f"已删除{label}「{clean}」。"


def list_items(store: ForbiddenStore, event: object, group_id: str) -> str:
    """列出本群违禁触发词和违禁样本。"""
    # 查询也属于管理能力，非管理员不能读取规则。
    if not is_admin(event):
        return REJECT_MESSAGE
    triggers = store.list_contents(group_id, FORBIDDEN_KIND_TRIGGER)
    samples = store.list_contents(group_id, FORBIDDEN_KIND_SAMPLE)
    # 两类都为空时用一句明确文案结束。
    if not triggers and not samples:
        return "本群还没有违禁触发词或违禁样本。"
    sections: list[str] = []
    sections.extend(_format_section("违禁触发词", triggers))
    sections.extend(_format_section("违禁样本", samples))
    return "\n".join(sections)


def _format_section(label: str, contents: list[str]) -> list[str]:
    """格式化一类配置，限制返回数量以避免群里刷屏。"""
    lines = [f"{label}（{len(contents)} 条）："]
    # 空类别也要明确显示，避免管理员误以为漏查。
    if not contents:
        lines.append("（无）")
        return lines
    for content in contents[:FORBIDDEN_LIST_LIMIT]:
        lines.append(f"「{content}」")
    # 超出上限时只报告剩余数量。
    if len(contents) > FORBIDDEN_LIST_LIMIT:
        rest = len(contents) - FORBIDDEN_LIST_LIMIT
        lines.append(f"（其余 {rest} 条未显示）")
    return lines
