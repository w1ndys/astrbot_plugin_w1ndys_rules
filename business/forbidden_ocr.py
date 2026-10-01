# 业务层：原图本地 OCR。不读协议 payload 的 ocr/text。没装或失败当没字。
# 测试可传入 reader。

import base64
import logging

_log = logging.getLogger("astrbot_plugin_w1ndys_rules")
_engine = None
_engine_failed = False


def ocr_text_from_b64(raw: str, reader=None) -> str:
    """base64 原图抽出可见文字。前缀已在采集时剥掉。"""
    data = _b64_to_bytes(raw)
    # 解不出字节就没有字
    if not data:
        return ""
    return ocr_text_from_bytes(data, reader)


def ocr_text_from_bytes(data: bytes, reader=None) -> str:
    """图片字节抽出可见文字。reader 命中就用它的返回。"""
    # 空图认不出字
    if not data:
        return ""
    # 测试注入，不打真实 RapidOCR
    if reader is not None:
        try:
            return _join_texts(reader(data))
        except Exception:  # noqa: BLE001 - 注入失败当没字，不误禁
            return ""
    return _rapid_ocr(data)


def _b64_to_bytes(raw: str) -> bytes:
    """把协议给的 base64 收成字节。坏值空字节。"""
    text = (raw or "").strip()
    # 空串解不出图
    if not text:
        return b""
    pad = (-len(text)) % 4
    # 协议端常省略末尾 =
    if pad:
        text = text + ("=" * pad)
    try:
        return base64.b64decode(text, validate=False)
    except Exception:  # noqa: BLE001 - 坏 base64 当没字
        return b""


def _rapid_ocr(data: bytes) -> str:
    """用 RapidOCR 认字。库缺失或异常当没字。"""
    engine = _load_engine()
    # 没装就不转写，后面不送模型
    if engine is None:
        _log.info("[rules] ocr skip reason=no_engine")
        return ""
    try:
        result = engine(data)
    except Exception:  # noqa: BLE001 - 推理失败当没字
        _log.info("[rules] ocr fail bytes=%s", len(data))
        return ""
    return _join_texts(result)

def _load_engine():
    """懒加载 RapidOCR。导入失败只试一次。"""
    global _engine, _engine_failed
    # 已经确定没有这个库
    if _engine_failed:
        return None
    # 已经建过就复用
    if _engine is not None:
        return _engine
    builder = _import_rapidocr()
    # 两个包名都没有
    if builder is None:
        _engine_failed = True
        _log.warning("[rules] ocr engine missing: install rapidocr")
        return None
    try:
        _engine = builder()
    except Exception:  # noqa: BLE001 - 权重加载失败当没装
        _engine_failed = True
        _log.warning("[rules] ocr engine init failed")
        return None
    return _engine


def _import_rapidocr():
    """先试新包 rapidocr，再试 rapidocr_onnxruntime。"""
    try:
        from rapidocr import RapidOCR

        return RapidOCR
    except ImportError:
        # 没装新包，试旧包名
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR
    except ImportError:
        # 两个包都没有，调用方当没装
        return None


def _join_texts(value: object) -> str:
    """把引擎输出收成换行文本。"""
    parts = _collect_texts(value)
    cleaned = []
    for item in parts:
        text = str(item).strip()
        # 空行丢掉
        if not text:
            continue
        cleaned.append(text)
    return "\n".join(cleaned)


def _collect_texts(value: object) -> list:
    """从 RapidOCR 常见返回形状里抠文字。"""
    # 没有输出
    if value is None:
        return []
    # 测试注入直接给字符串
    if isinstance(value, str):
        return [value]
    txts = getattr(value, "txts", None)
    # 新接口 RapidOCROutput.txts
    if txts:
        return list(txts)
    rec = getattr(value, "rec_texts", None)
    # 另一字段名也是识别结果
    if rec:
        return list(rec)
    # 老接口 (result, elapse)
    if isinstance(value, tuple) and value:
        return _collect_texts(value[0])
    # [[box, text, score], ...]
    if isinstance(value, list):
        return _texts_from_rows(value)
    return [value]


def _texts_from_rows(rows: list) -> list:
    """从 [框, 字, 分] 行里取字。纯字符串行也收。"""
    texts = []
    for row in rows:
        # 有的版本直接给字符串列表
        if isinstance(row, str):
            texts.append(row)
            continue
        # 标准三元组第二项是字
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            texts.append(row[1])
    return texts
