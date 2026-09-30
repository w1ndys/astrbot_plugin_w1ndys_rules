# 业务层：本地二维码检出。用 QReader；没装或失败当未检出，不误禁。
# 检出即违禁，不看载荷。测试可传入 decoder。

import base64
import io

_qreader = None
_qreader_failed = False


def qr_found_in_bytes(data: bytes, decoder=None) -> bool:
    """这组字节里有没有二维码。decoder 命中就 True。"""
    # 空图解不了
    if not data:
        return False
    # 测试注入，不打真实 QReader
    if decoder is not None:
        try:
            return bool(decoder(data))
        except Exception:  # noqa: BLE001 - 注入解码失败当未检出
            return False
    return _qreader_found(data)



def qr_found_in_b64(raw: str, decoder=None) -> bool:
    """base64 图有没有二维码。前缀已在采集时剥掉。"""
    text = (raw or "").strip()
    # 空串解不出图
    if not text:
        return False
    pad = (-len(text)) % 4
    # 协议端常省略末尾 =
    if pad:
        text = text + ("=" * pad)
    try:
        data = base64.b64decode(text, validate=False)
    except Exception:  # noqa: BLE001 - 坏 base64 当未检出，继续转写
        return False
    return qr_found_in_bytes(data, decoder)



def _qreader_found(data: bytes) -> bool:
    """用 QReader 检出即 True。库缺失或异常当未检出。"""
    reader = _load_qreader()
    # 没装 QReader 就跳过这一层
    if reader is None:
        return False
    image = _bytes_to_rgb(data)
    # 转不成图就当没解出来
    if image is None:
        return False
    try:
        return _reader_hit(reader, image)
    except Exception:  # noqa: BLE001 - 解码超时或模型异常不能误禁
        return False


def _load_qreader():
    """懒加载一个 QReader。导入失败只试一次。"""
    global _qreader, _qreader_failed
    # 已经确定没有这个库
    if _qreader_failed:
        return None
    # 已经建过就复用
    if _qreader is not None:
        return _qreader
    try:
        from qreader import QReader
    except ImportError:
        _qreader_failed = True
        return None
    try:
        _qreader = QReader()
    except Exception:  # noqa: BLE001 - 权重加载失败当没装
        _qreader_failed = True
        return None
    return _qreader


def _reader_hit(reader: object, image: object) -> bool:
    """有 detect 就看框；否则看 decode 出的非空载荷。"""
    detect = getattr(reader, "detect", None)
    # detect 只回答有没有码，不看内容
    if callable(detect):
        boxes = detect(image=image)
        return _has_items(boxes)
    decode = getattr(reader, "detect_and_decode", None)
    # 老接口只返回文本
    if not callable(decode):
        return False
    texts = decode(image=image)
    # 一个非空载荷就够
    for item in texts or []:
        # 空串不是码
        if item:
            return True
    return False


def _has_items(value: object) -> bool:
    """列表、元组、数组有元素才算检出。"""
    # 解码器没返回
    if value is None:
        return False
    try:
        return len(value) > 0
    except TypeError:
        # 单个框对象也算检出
        return bool(value)



def _bytes_to_rgb(data: bytes):
    """把图片字节收成 QReader 要的 RGB 数组。失败返回 None。"""
    try:
        import numpy as np
        from PIL import Image as PILImage
    except ImportError:
        # 没装 pillow/numpy 就不能喂 QReader，当未检出
        return None

    try:
        pil = PILImage.open(io.BytesIO(data))
        rgb = pil.convert("RGB")
        return np.asarray(rgb)
    except Exception:  # noqa: BLE001 - 坏图当未检出
        return None
