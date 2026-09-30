# 业务层：图片转写的规则门。不复用全局触发词，不处置。
# 命中才有资格送「是/否」模型。

import re

_DOMAIN = re.compile(
    r"(?:https?://)?"
    r"(?:[a-z0-9-]+\.)+[a-z]{2,}"
    r"(?:/\S*)?",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_QQ = re.compile(r"(?:qq|QQ)[:：\s]*\d{5,12}")
_COMBO_NEEDLES = ("网址", "全国", "随时", "上门", "玩")
_CONTACT_NEEDLES = ("扫码加", "加微", "微信号")


def image_rule_hit(transcript: str) -> str:
    """转写命中哪条图片规则。没命中返回空串。"""
    text = transcript.strip()
    # 空转写没有硬信号
    if not text:
        return ""
    packed = _pack_domain_text(text)
    # 域名或 URL 一个就够送模型
    if _DOMAIN.search(packed) or _DOMAIN.search(text):
        return "域名"
    # 手机号
    if _PHONE.search(text):
        return "联系方式"
    # QQ 号写法
    if _QQ.search(text):
        return "联系方式"
    for needle in _CONTACT_NEEDLES:
        # 加微、扫码加这类联系口令
        if needle in text:
            return "联系方式"
    # 约饭单独不够，要配引流词
    if _combo_hit(text):
        return "招嫖搭配"
    return ""


def _pack_domain_text(text: str) -> str:
    """去掉空白，方便识别插空格的短域名。"""
    return re.sub(r"\s+", "", text)


def _combo_hit(text: str) -> bool:
    """约 再配 全国/随时/上门/玩/网址 才算组合信号。"""
    # 没有「约」就不是这套搭配
    if "约" not in text:
        return False
    for needle in _COMBO_NEEDLES:
        # 第二个信号出现才送模型，避免约饭误伤
        if needle in text:
            return True
    return False
