# 实体层：一条关键词回复规则。只描述数据形状，不负责存取。


class KeywordRule:
    """群里的一条关键词回复：整条消息等于 keyword 时，回 reply。"""

    def __init__(self, group_id: str, keyword: str, reply: str) -> None:
        # 群号决定这条规则在哪个群生效，同一个关键词在不同群可以是不同回复。
        self.group_id = group_id
        # 关键词按「完全相等」匹配，不做包含匹配。
        self.keyword = keyword
        # 命中后原样发出去的文本。
        self.reply = reply
