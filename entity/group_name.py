# 实体层：一条群号到群名的映射。只描述数据形状，不负责存取。


class GroupName:
    """一个群在 Pages 上显示用的名字。主键是群号。"""

    def __init__(self, group_id: str, group_name: str) -> None:
        # 群号是映射主键，和功能名单、欢迎语、关键词用同一套字符串。
        self.group_id = group_id
        # 展示名来自 OneBot get_group_list，空串表示还没拉到。
        self.group_name = group_name
