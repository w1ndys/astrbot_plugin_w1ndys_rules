# 实体层：一条按群保存的违禁触发词或违禁样本。


class ForbiddenItem:
    """违禁配置条目。kind 区分触发词和样本，content 保存原文。"""

    def __init__(self, group_id: str, kind: str, content: str) -> None:
        """保存数据库读取出的三个业务字段。"""
        self.group_id = group_id
        self.kind = kind
        self.content = content
