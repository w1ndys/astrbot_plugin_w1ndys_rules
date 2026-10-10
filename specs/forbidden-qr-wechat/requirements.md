# Requirements Document

## Introduction

群图片和 4.0 秒以内短视频帧的二维码热路径现在只调用 QReader。QReader 先跑检测模型再解码，本机对照里中位耗时约 243 毫秒。同一张低对比 QQ 群码上，OpenCV contrib 的微信二维码检测器中位约 29 毫秒，且能解出载荷。QReader 已经装在运行容器里，并且能把「有框但没有文本」也当成检出。微信接口只返回解出的文本，做不到这件事。

本功能把热路径改成三级本地解码，顺序固定：微信检测器、zxing-cpp、QReader。前一级已经检出时，不调用后面的级。检出仍表示违禁，不按载荷内容放行。图片检测测试页要显示是哪一层检出的。

zxing-cpp 在一次普通读取里尽量多认二维家族和其他二维码，不开启会明显变慢的增强开关，也不认商品一维码。QReader 仍保留现有口径：有检测框，或有非空文本，都算检出。

## Glossary

- **违禁业务层**: `business/forbidden_qr.py` 及其调用方。调用方包括图片路、短视频抽帧和图片检测测试。
- **微信检测器**: `cv2.wechat_qrcode.WeChatQRCode`。本功能用无参构造，再调用 `detectAndDecode`。
- **zxing 层**: `zxingcpp.read_barcodes` 的一次普通读取。只采纳本文件「已拟定」里列出的格式，且文本去空白后非空。
- **QReader 层**: 现有 `QReader`。有 `detect` 返回的框，或有非空文本，都算这一层检出。
- **检出**: 三级里任意一级按该级口径命中。空字符串不算文本。
- **命中层**: `wechat`、`zxing` 或 `qreader`。未检出时为空字符串。
- **引擎总状态**: `ready`、`missing`、`init_failed` 三者之一。`ready` 表示三级里至少一个已构造成功。
- **分层状态**: 微信检测器、zxing、QReader 各自的 `ready`、`missing`、`init_failed`。
- **热路径**: 群消息里的图片 base64 和短视频帧字节。热路径只消费布尔检出，不消费诊断字段。
- **图片检测测试**: 现有控制台页。本功能只改该页的二维码展示，不改上传限制、OCR、触发词、模型，也不增加处置。

## 已拟定

下列取值写进本文件，作为本轮设计的默认。确认 spec 前可以改。

1. 顺序固定为微信检测器、zxing-cpp、QReader。前一级检出后不调用后面的级。
2. 任一解码器构造成功，引擎总状态就是 `ready`。三级都导入失败才是 `missing`。至少导入成功一个、且没有任何一个构造成功，才是 `init_failed`。
3. zxing 一次调用认这些格式：QR Code、Micro QR、rMQR、Aztec、Data Matrix、PDF417。不认 EAN、UPC、Code 128、Code 39、ITF、Codabar。不开启 `try_harder`、`try_rotate`、`try_invert`。
4. QReader 保持现有口径：有检测框即检出；没有 `detect` 时，非空文本也检出。微信层和 zxing 层必须有非空文本。
5. 诊断字段 `box_count` 保留原名。微信层和 zxing 层表示非空文本条数；QReader 层有框时表示框数，没框时表示非空文本条数。页面标签改为「检出数量」。
6. `requirements.txt` 保留 `qreader`，追加不带版本号的 `opencv-contrib-python` 和 `zxing-cpp`。`rapidocr` 与 `onnxruntime` 保留。

## Requirements

### Requirement 1：热路径按三级顺序解码

**User Story:** 作为群管理员，我要常见二维码先走微信检测器，以便同一条群消息少等一次 QReader 检测模型。

#### Acceptance Criteria

1. WHEN 热路径收到非空图片字节且未注入测试解码器, 违禁业务层 SHALL 先调用已构造的微信检测器。
2. WHEN 微信检测器返回至少一条去空白后非空的文本, 违禁业务层 SHALL 返回检出，且不调用 zxing-cpp 和 QReader。
3. WHEN 微信检测器未返回非空文本或调用抛出异常, 违禁业务层 SHALL 调用已构造的 zxing 层。
4. WHEN zxing 层返回至少一条已拟定格式且去空白后非空的文本, 违禁业务层 SHALL 返回检出，且不调用 QReader。
5. WHEN 微信检测器和 zxing 层都未检出, 违禁业务层 SHALL 调用已构造的 QReader。
6. WHEN QReader 的 `detect` 返回至少一框, 违禁业务层 SHALL 返回检出。
7. IF QReader 没有 `detect` 且返回至少一条非空文本, 违禁业务层 SHALL 返回检出。
8. IF 图片字节不能解码成图像, 违禁业务层 SHALL 返回未检出，且不调用三级解码器。

### Requirement 2：引擎缺失与未检出可以分开判断

**User Story:** 作为管理员，我要知道漏检是因为解码器没装，还是因为这张图没有被任何一级检出，以便部署后能核对容器依赖。

#### Acceptance Criteria

1. WHEN 三级解码器至少一个构造成功, 违禁业务层 SHALL 把引擎总状态报为 `ready`。
2. IF 三级库都导入失败, 违禁业务层 SHALL 把引擎总状态报为 `missing`，热路径返回未检出。
3. IF 至少一个库导入成功且三级解码器都构造失败, 违禁业务层 SHALL 把引擎总状态报为 `init_failed`，热路径返回未检出。
4. WHEN 引擎总状态不是 `ready`, 违禁业务层 SHALL 在本进程内记录一次 warning，文案包含引擎总状态。
5. WHILE 同一个进程再次遇到某一级已经失败的加载, 违禁业务层 SHALL 复用该级的加载结果，不再重复导入。
6. WHEN 前一级已经返回检出, 违禁业务层 SHALL 不导入尚未加载的后一级库。

### Requirement 3：对外布尔接口和处置口径保持不变

**User Story:** 作为群管理员，我要加前两级之后图片、短视频和 base64 入口的违禁口径不变，以便不重做撤回、禁言和飞书流程。

#### Acceptance Criteria

1. WHEN 图片路或短视频帧调用二维码检测, 违禁业务层 SHALL 继续通过 `qr_found_in_bytes` 或 `qr_found_in_b64` 返回布尔值。
2. WHEN 任一入口返回检出, 违禁业务层 SHALL 沿用现有二维码原因和文案处置，且不读取载荷决定是否放行。
3. WHEN 调用方传入 `decoder`, 违禁业务层 SHALL 只使用该替身判断检出，不调用三级真实解码器。
4. IF 替身抛出异常, 违禁业务层 SHALL 返回未检出。
5. WHEN 微信层或 zxing 层已经检出, 违禁业务层 SHALL 不构造 QReader。

### Requirement 4：图片检测测试页显示命中层

**User Story:** 作为管理员，我要在图片检测测试页看到是哪一级检出的，以便用同一张已知含码的图核对快速层和 QReader 兜底。

#### Acceptance Criteria

1. WHEN 图片检测测试收到可解码图片, 违禁业务层 SHALL 返回引擎总状态、三个分层状态、是否检出、命中层、检出数量、截断载荷和错误名。
2. WHEN 微信检测器解出非空文本, 违禁业务层 SHALL 把命中层标为 `wechat`，且诊断结果不包含后两级的载荷。
3. WHEN 只有 zxing 层解出非空文本, 违禁业务层 SHALL 把命中层标为 `zxing`，且不调用 QReader。
4. WHEN 只有 QReader 检出, 违禁业务层 SHALL 把命中层标为 `qreader`。
5. WHEN 已构造的各级都未检出, 违禁业务层 SHALL 返回未检出，命中层为空字符串。
6. WHEN 检测返回且引擎总状态为 `ready`, 控制台 SHALL 展示命中层、检出数量和截断载荷。
7. IF 引擎总状态不是 `ready`, 控制台 SHALL 显示「二维码引擎未加载，本次未识别」，并展示三个分层状态。
8. WHEN 图片检测测试完成, 插件 SHALL 保持不撤回、不禁言、不发飞书、不写违禁日志。

### Requirement 5：依赖声明追加快速解码器

**User Story:** 作为维护者，我要仓库同时声明微信检测器、zxing-cpp 和现有 QReader，以便新环境按声明安装后三级都能用。

#### Acceptance Criteria

1. WHEN 阅读 `requirements.txt`, 维护者 SHALL 看到 `opencv-contrib-python`、`zxing-cpp` 和 `qreader`。
2. WHEN 阅读 `requirements.txt`, 维护者 SHALL 看到原有 `rapidocr` 和 `onnxruntime` 仍在。
3. IF 运行环境缺少前两级库, 插件 SHALL 完成加载；QReader 可用时引擎总状态为 `ready`，三级都不可用时留在 `missing` 或 `init_failed`，且不因缺库中断其他违禁规则。
