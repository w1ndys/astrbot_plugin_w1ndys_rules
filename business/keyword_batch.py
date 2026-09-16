# 业务层：管理员用独立命令批量导入关键词，不经过模型。
#
# 单条增删改查可以交给自然语言工具；一次贴几十行不能指望模型逐条调工具。
# 这条路径只认固定文本格式，权限和校验都在服务器端做完再落库。
#
# 已有关键词一律报冲突、不覆盖：批量导入是搬家，不是改一条。要改回复走
# 自然语言的「改」。本批里重复的关键词只收下第一次，后面的算跳过。

from ..data.keyword_store import KeywordStore
from ..entity.constants import KEYWORD_BATCH_DETAIL_LIMIT, KEYWORD_BATCH_MAX_LINES
from .auth import is_admin
from .keyword_admin import REJECT_MESSAGE, check_keyword, check_reply
from .wake_prefix import format_command

# 一行里关键词和回复的分隔符。中文输入法常打出全角竖线，表格粘贴常带 Tab。
_SEPARATORS = ("|", "｜", "\t")


def usage_text(context: object) -> str:
    """没有贴内容时的用法说明。指令写法带上本机实际唤醒前缀。"""
    command = format_command(context, "关键词 批量")
    return (
        f"用法：在「{command}」后面换行，一行一条，关键词和回复用 | 分开。"
        "已有关键词会报冲突，不会覆盖。\n"
        "示例：\n"
        f"{command}\n"
        "原神|好玩\n"
        "你好|你好呀"
    )


def strip_command_header(text: str) -> str:
    """去掉命令本身，留下要导入的行。唤醒前缀在进插件前就已经被剥掉了。"""
    payload = text.replace("\ufeff", "")
    lines = payload.splitlines()
    # 空消息没有可导入的行
    if not lines:
        return ""
    first = lines[0].strip()
    extra = ""
    rest = lines[1:]
    # 第一行只是命令，数据在后面的换行里
    if first == "关键词 批量" or first == "批量":
        extra = ""
    # 命令和第一条数据写在同一行
    elif first.startswith("关键词 批量"):
        extra = first[len("关键词 批量") :].strip()
    # 只剥独立的「批量」，不要把「批量|回复」这种数据行当命令
    elif first.startswith("批量") and (len(first) == 2 or first[2] in " \t"):
        extra = first[2:].strip()
    else:
        # 命令过滤器可能已经把「关键词 批量」剥掉，第一行就是数据
        return payload
    # 同一行里命令后面还带着第一条，要拼回正文
    if extra:
        return "\n".join([extra, *rest])
    return "\n".join(rest)


def split_keyword_reply(line: str) -> tuple[str, str] | None:
    """按第一个分隔符切开。找不到分隔符就返回 None，由调用方记成跳过。"""
    found_at = -1
    found_sep = ""
    for sep in _SEPARATORS:
        idx = line.find(sep)
        # 这个分隔符没出现，试下一个
        if idx < 0:
            continue
        # 同时出现多种分隔符时，用最靠前的那个，避免把回复里的 | 切错
        if found_at < 0 or idx < found_at:
            found_at = idx
            found_sep = sep
    # 整行都没有分隔符，调用方会记成跳过
    if found_at < 0:
        return None
    return line[:found_at], line[found_at + len(found_sep) :]


def _count_data_lines(payload: str) -> int:
    """数非空行。空行是粘贴噪声，不计入上限。"""
    count = 0
    for raw_line in payload.splitlines():
        # 有内容的行才算一条导入
        if raw_line.strip():
            count += 1
    return count


def _classify_line(
    context: object,
    keywords: KeywordStore,
    group_id: str,
    line_no: int,
    line: str,
    seen: set[str],
) -> tuple[str, str, str]:
    """判断一行该新增、冲突还是跳过。返回 (动作, 关键词, 说明)。"""
    parts = split_keyword_reply(line)
    # 没有分隔符就无法拆出关键词和回复
    if parts is None:
        return "skip", "", f"第 {line_no} 行没有用「|」分开关键词和回复"
    clean_keyword, error = check_keyword(context, parts[0])
    # 关键词不合法，这条不写库
    if error:
        return "skip", "", f"第 {line_no} 行{error}"
    clean_reply, error = check_reply(parts[1])
    # 回复不合法，这条不写库
    if error:
        return "skip", "", f"第 {line_no} 行{error}"
    # 本批重复只收下第一次，避免后写的盖掉先写的
    if clean_keyword in seen:
        return "skip", clean_keyword, f"「{clean_keyword}」在本批里重复，只收下第一次"
    # 库里已有则报冲突，批量导入不覆盖
    if keywords.rule_of(group_id, clean_keyword) is not None:
        return "conflict", clean_keyword, ""
    return "add", clean_keyword, clean_reply


async def import_rules(
    context: object,
    keywords: KeywordStore,
    event: object,
    group_id: str,
    raw_text: str,
) -> str:
    """导入一批规则。返回发到群里的整段文案。"""
    # 非管理员不能往库里写，也不透露本群有哪些词
    if not is_admin(event):
        return REJECT_MESSAGE
    payload = strip_command_header(raw_text)
    # 只发了命令没贴内容，回用法而不是空成功
    if not payload.strip():
        return usage_text(context)
    data_line_count = _count_data_lines(payload)
    # 一次贴太多多半是误操作，整批拒绝以免把库撑爆
    if data_line_count > KEYWORD_BATCH_MAX_LINES:
        return (
            f"一次最多导入 {KEYWORD_BATCH_MAX_LINES} 条，这次有 {data_line_count} 条，"
            "请拆开再发。这次没有写入。"
        )
    return await _import_lines(context, keywords, group_id, payload)


async def _import_lines(
    context: object,
    keywords: KeywordStore,
    group_id: str,
    payload: str,
) -> str:
    """逐行分类后只写入新增项，再拼回报。"""
    added: list[tuple[str, str]] = []
    conflicts: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for line_no, raw_line in enumerate(payload.splitlines(), start=1):
        line = raw_line.strip()
        # 空行多半是粘贴时带上的，不算一条，也不报跳过
        if not line:
            continue
        action, keyword, extra = _classify_line(
            context, keywords, group_id, line_no, line, seen
        )
        # 跳过的行只记原因，不写库
        if action == "skip":
            skipped.append(extra)
            continue
        seen.add(keyword)
        # 已有规则留给管理员用单条修改，这里不覆盖
        if action == "conflict":
            conflicts.append(keyword)
            continue
        added.append((keyword, extra))
    await keywords.upsert_many(group_id, added)
    return _report(added, conflicts, skipped)


def _report(
    added: list[tuple[str, str]],
    conflicts: list[str],
    skipped: list[str],
) -> str:
    """汇总新增 / 冲突 / 跳过。明细有上限，避免一次贴太多把群刷屏。"""
    lines = [
        (
            f"批量导入完成：新增 {len(added)} 条，"
            f"冲突 {len(conflicts)} 条，跳过 {len(skipped)} 条。"
        )
    ]
    # 把没覆盖的词列出来，方便管理员改用单条修改
    if conflicts:
        lines.append("冲突（已有规则，未覆盖）：")
        lines.extend(_limited([f"「{keyword}」" for keyword in conflicts]))
    # 把没写进去的原因列出来，方便对照原文改
    if skipped:
        lines.append("跳过：")
        lines.extend(_limited(skipped))
    return "\n".join(lines)


def _limited(items: list[str]) -> list[str]:
    """超出上限时只列前几条，并补一句其余条数。"""
    visible = items[:KEYWORD_BATCH_DETAIL_LIMIT]
    rest = len(items) - len(visible)
    # 明细太长会刷屏，剩下的只报数量
    if rest > 0:
        visible.append(f"（其余 {rest} 条未显示）")
    return visible
