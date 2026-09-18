# 实体层：一条邀请边。按群存，记录谁把谁拉进了群。
# 只描述数据形状，不负责存取。


class InviteEdge:
    """一条入群邀请关系：user_id 是本群成员，inviter_id 是把他拉进来的人。"""

    def __init__(
        self, group_id: str, user_id: str, inviter_id: str, sub_type: str
    ) -> None:
        # 群号决定这条边属于哪棵树，同一个人的邀请关系按群分开记。
        self.group_id = group_id
        # 被邀请进群的成员 QQ 号。
        self.user_id = user_id
        # 邀请人。approve 入群时记的是审批管理员，不是真实邀请人。
        self.inviter_id = inviter_id
        # OneBot 的 sub_type：invite 是被人拉进来，approve 是审批通过。
        self.sub_type = sub_type
