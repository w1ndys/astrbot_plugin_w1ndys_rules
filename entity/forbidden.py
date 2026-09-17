# 实体层：一条违禁配置。触发词全局共用，group_id 存固定作用域键。


class ForbiddenItem:
    """违禁配置条目。当前业务只写触发词，content 保存原文。"""

    def __init__(self, group_id: str, kind: str, content: str) -> None:
        """保存数据库读取出的三个业务字段。"""
        self.group_id = group_id
        self.kind = kind
        self.content = content
