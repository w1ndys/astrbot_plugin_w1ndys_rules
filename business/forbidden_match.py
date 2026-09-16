# 业务层：违禁词触发词的包含匹配。不进大模型，不处置。
#
# 触发词来自 WebUI 全局配置，一行一个。消息里包含任一触发词才算命中，
# 英文不区分大小写，中文按原文包含。


def parse_trigger_words(raw: str) -> list[str]:
    """把 WebUI 多行文本收成触发词列表。空行丢掉。"""
    words: list[str] = []
    # 没配或配成空串就没有任何触发词，后面不会误命中
    if not raw:
        return words
    for line in raw.splitlines():
        text = line.strip()
        # 空行和纯空白不是触发词
        if not text:
            continue
        words.append(text)
    return words


def find_trigger(text: str, words: list[str]) -> str:
    """在消息里找第一个命中的触发词。找不到返回空串。"""
    # 没有文本或没有词，不可能命中
    if not text or not words:
        return ""
    haystack = text.casefold()
    for word in words:
        needle = word.casefold()
        # 空白词不当触发词，避免空串包含在任何消息里
        if not needle:
            continue
        # 包含即命中，英文大小写已经折到同一套字符
        if needle in haystack:
            return word
    return ""
