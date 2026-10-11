# 命中日志：payload 里的签名和 token 打码，其余字段保留。
#
# 样本字段取自线上真实 payload，签名值换成占位。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
# 测试从仓库根的上一级导入包名 astrbot_plugin_w1ndys_rules
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.hit_log import (
    hit_line,
    mask_payload,
    mask_query,
)


class MaskQueryTest(unittest.TestCase):
    # 地址查询串里只遮敏感参数

    def test_auth_sig_is_masked(self) -> None:
        # 群名片的跳转地址带签名，必须遮掉值
        masked = mask_query("mqqapi://card/show_pslcard?authSig=SECRET&biz=1")
        self.assertIn("authSig=[已打码]", masked)
        self.assertNotIn("SECRET", masked)
        # 非敏感参数留着，排查时还能看出这条地址是干什么的
        self.assertIn("biz=1", masked)

    def test_plain_text_is_kept(self) -> None:
        # 不含问号的普通文字原样返回
        self.assertEqual(mask_query("普通文本"), "普通文本")


class MaskPayloadTest(unittest.TestCase):
    # 字典按字段名遮值

    def test_token_value_is_masked(self) -> None:
        # 卡片 config.token 是签名类字段，必须遮
        masked = mask_payload({"config": {"token": "SECRET", "width": 526}})
        self.assertEqual(masked["config"]["token"], "[已打码]")
        # 同一个对象里的普通字段不能跟着被遮
        self.assertEqual(masked["config"]["width"], 526)

    def test_readable_fields_are_kept(self) -> None:
        # 昵称这类可读字段要留着，日志才有排查价值
        masked = mask_payload({"meta": {"contact": {"nickname": "卷心菜大军"}}})
        self.assertEqual(masked["meta"]["contact"]["nickname"], "卷心菜大军")

    def test_list_items_are_masked(self) -> None:
        # 列表逐项递归，藏在列表里的签名也要遮
        masked = mask_payload([{"authSig": "SECRET"}])
        self.assertEqual(masked[0]["authSig"], "[已打码]")

    def test_other_types_are_kept(self) -> None:
        # 数字和布尔不是密钥，原样保留
        self.assertEqual(mask_payload(526), 526)
        self.assertIs(mask_payload(True), True)


class HitLineTest(unittest.TestCase):
    # 那一行本身

    def test_line_has_group_user_and_payload(self) -> None:
        # 群号、发言人、payload 三样都要在同一行
        line = hit_line("123", "456", '{"a":1}')
        self.assertIn("群号=123", line)
        self.assertIn("发言人=456", line)
        self.assertIn('payload={"a":1}', line)
