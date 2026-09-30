# 图片转写规则门：域名、联系方式、约+引流。不复用全局触发词。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = str(ROOT.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from astrbot_plugin_w1ndys_rules.business.forbidden_image_rule import image_rule_hit

LEAK = (
    "这是一张手机聊天截图，聊天对象名为“年糕”。对方先发消息“建材王总”和"
    "“你最近出差去哪玩了”，随后绿色气泡回复：“我都在6m3p.cc上面约的”和"
    "“全国随时随地都可以玩”。"
)


class ImageRuleTest(unittest.TestCase):
    def test_leak_transcript_hits_domain(self) -> None:
        self.assertEqual(image_rule_hit(LEAK), "域名")

    def test_about_dinner_skips(self) -> None:
        self.assertEqual(image_rule_hit("晚上约饭"), "")

    def test_combo_without_domain(self) -> None:
        self.assertEqual(image_rule_hit("约全国随时上门"), "招嫖搭配")

    def test_empty(self) -> None:
        self.assertEqual(image_rule_hit(""), "")


    def test_phone_is_contact(self) -> None:
        self.assertEqual(image_rule_hit("电话13812345678"), "联系方式")

    def test_qq_is_contact(self) -> None:
        self.assertEqual(image_rule_hit("QQ：123456"), "联系方式")

    def test_wechat_needle(self) -> None:
        self.assertEqual(image_rule_hit("加微找我"), "联系方式")

