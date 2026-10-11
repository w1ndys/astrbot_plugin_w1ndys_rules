# 联系人卡片身份：群名片取群号和群名，推荐好友取账号，缺字段有兜底。
#
# 样本字段取自线上真实 payload，查询串和签名不写进仓库。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.group_card import card_identity
from astrbot_plugin_w1ndys_rules.entity.constants import CARD_IDENTITY_MAX_LEN

# 线上群名片：群号在头像地址的 gh/<群号> 段里，contact 字段是短横线
GROUP_CARD = {
    "app": "com.tencent.contact.lua",
    "prompt": "群名片: 卷心菜大军",
    "bizsrc": "qun.share",
    "view": "contact",
    "meta": {
        "contact": {
            "avatar": "https://p.qlogo.cn/gh/728077087/728077087_19/100",
            "contact": "-",
            "nickname": "卷心菜大军",
            "tag": "群名片",
        }
    },
}

# 线上推荐好友：账号直接写在 contact 字段里
FRIEND_CARD = {
    "app": "com.tencent.contact.lua",
    "prompt": "推荐联系人：w1ndys",
    "bizsrc": "cardshare.cardshare",
    "view": "contact",
    "meta": {
        "contact": {
            "contact": "账号：2769731875",
            "nickname": "w1ndys",
            "tag": "推荐好友",
        }
    },
}


class CardIdentityTest(unittest.TestCase):
    # 校验四类身份拼装和兜底

    def test_group_card_has_group_no_and_name(self) -> None:
        # 群号要从头像路径解出来，否则管理员看不出宣传的是哪个群
        self.assertEqual(
            card_identity(GROUP_CARD), "群名片：群号 728077087 群名 卷心菜大军"
        )

    def test_group_card_without_avatar_keeps_name(self) -> None:
        # 解不出群号时只写群名，不能返回空串
        card = {"meta": {"contact": {"nickname": "卷心菜大军", "tag": "群名片"}}}
        self.assertEqual(card_identity(card), "群名片：群名 卷心菜大军")

    def test_friend_card_reports_account(self) -> None:
        # 推荐好友要给出 QQ 号，并去掉「账号：」这个给人看的标签
        self.assertEqual(card_identity(FRIEND_CARD), "推荐好友：2769731875")

    def test_missing_contact_falls_back(self) -> None:
        # contact 不是对象时也不能返回空串，至少要有一句话
        card = {"meta": {"contact": "不是对象"}}
        self.assertEqual(card_identity(card), "联系人卡片")

    def test_long_identity_is_clipped(self) -> None:
        # 卡片字段来自外部输入，超长必须截断，避免撑爆日志和飞书
        card = {"meta": {"contact": {"tag": "推荐好友", "nickname": "x" * 300}}}
        self.assertEqual(len(card_identity(card)), CARD_IDENTITY_MAX_LEN)
