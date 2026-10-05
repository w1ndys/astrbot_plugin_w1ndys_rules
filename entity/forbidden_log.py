# 实体层：一条违禁命中日志。只描述数据形状，不负责存取。


class ForbiddenLog:
    """一次真实违禁处置留下的记录。原文三列给详情页，列表不要直接拿来展示。"""

    def __init__(
        self,
        log_id: int,
        group_id: str,
        user_id: str,
        reason_code: str,
        reason_text: str,
        created_at: str,
        text: str,
        json_text: str,
        images: str,
        sender_name: str,
    ) -> None:
        """保存从库里读出的字段。json_text 对应列名 json。sender_name 是命中当时的群昵称快照，空串表示当时没有或还没回补。"""
        self.id = log_id
        self.group_id = group_id
        self.user_id = user_id
        self.reason_code = reason_code
        self.reason_text = reason_text
        self.created_at = created_at
        self.text = text
        self.json_text = json_text
        self.images = images
        # 群昵称快照，只属于这一条日志；群名不进这张表的任何列
        self.sender_name = sender_name
