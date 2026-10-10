// 页面层：图片检测测试面板。结果来自三级本地解码（微信、zxing、QReader）和 RapidOCR。不会撤回、禁言、发飞书或写日志。

import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Space, Upload } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type { ImageOcrDiagnosis, ImageQrDiagnosis, ImageTestResult } from "./types";

// 后端只认这四种图片类型，多一种就会在入口拒掉，所以本地先挡一次
const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

// 后端的上传上限（8MB），这里先拦下省掉一次往返
const MAX_IMAGE_BYTES = 8388608;

// 引擎跑起来的状态值，和后端报告里的 ready 一致
const ENGINE_READY = "ready";

// 预检没过时后端给空对象，页面按这句显示，不能当成「已识别且无码」
const NOT_INSPECTED = "本次未检测";

// 某一层本次没走到时后端给空串，页面按这句显示，不能当成「这一层没装库」
const LAYER_NOT_LOADED = "本次未加载";

// 二维码引擎没加载时的固定文案，避免误读成图里没码
const QR_ENGINE_MISSING = "二维码引擎未加载，本次未识别";

// 引擎不是 ready 时，数量和载荷不能写成「未检出」或「本次未检测」
const QR_COUNT_NOT_RECOGNIZED = "本次未识别";

// OCR 引擎没加载时的固定文案，避免误读成识别过但没字
const OCR_ENGINE_MISSING = "OCR 引擎未加载，本次未识别";

// Descriptions 的一行：标签加值
interface ResultLine {
  key: string;
  label: string;
  children: string;
}

// 校验选中的文件。空串表示放行，非空就是给用户看的原因。
function checkImage(file: File): string {
  // 类型不在白名单：后端只收这四种，说明原因后不发请求
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
    return "只支持 PNG、JPEG、WebP、GIF 四种图片。";
  }
  // 超过 8MB：后端会按坏请求回 400，这里先拦下
  if (file.size > MAX_IMAGE_BYTES) {
    return "图片超过 8MB，请压缩后再上传。";
  }
  return "";
}

// 状态后面带上后端给的错误标记，用来区分「引擎没装」和「这张图读不出来」
function engineText(engine: string, error: string | undefined): string {
  // 有错误码就拼在状态后面，页面只显示错误名，不显示图片字节
  if (error) {
    return engine + "（" + error + "）";
  }
  return engine;
}

// 二维码区的引擎状态行：总状态为空串说明这次根本没试到引擎，先补状态名再拼错误码
function engineSummaryText(engine: string, error: string | undefined): string {
  // 空串直接拼错误码会显示成「（bad_image）」，看不出状态，所以换成「本次未加载」
  if (!engine) {
    return engineText(LAYER_NOT_LOADED, error);
  }
  return engineText(engine, error);
}

// 分层状态：后端报空串说明本次没走到这一层，显示「本次未加载」，不写成 missing
function layerStateText(state: string | undefined): string {
  // 空串和缺失都算没加载过，直接把空串写出来会被读成「这一层没装库」
  if (!state) {
    return LAYER_NOT_LOADED;
  }
  return state;
}

// 命中层翻译成页面用词：微信、zxing、QReader 各自的名字，未检出写「无」
function layerText(layer: string | undefined): string {
  // 后端只报三个已知取值，其余（含空串和缺失）都当未检出
  if (layer === "wechat") {
    return "微信";
  }
  // zxing 的显示名就是库名，不翻译
  if (layer === "zxing") {
    return "zxing";
  }
  // QReader 同样用库名显示，方便和日志里对上
  if (layer === "qreader") {
    return "QReader";
  }
  return "无";
}

// 三个分层状态：ready 和非 ready 两支都要摆出来，抽一处免得两处写岔
function qrLayerLines(qr: ImageQrDiagnosis): ResultLine[] {
  return [
    { key: "qr-wechat", label: "微信分层状态", children: layerStateText(qr.wechat) },
    { key: "qr-zxing", label: "zxing 分层状态", children: layerStateText(qr.zxing) },
    { key: "qr-qreader", label: "QReader 分层状态", children: layerStateText(qr.qreader) },
  ];
}

// 二维码区要显示的几行。引擎没跑过或没加载时都必须写明没识别，不能显示成未检出。
function qrLines(qr: ImageQrDiagnosis): ResultLine[] {
  // 字段缺失才是预检没过。空串是后端明确给的「这次没试到引擎」，不能和缺失混成一档
  if (qr.engine === undefined) {
    return [
      { key: "qr-engine", label: "引擎状态", children: NOT_INSPECTED },
      ...qrLayerLines(qr),
      { key: "qr-found", label: "是否检出", children: NOT_INSPECTED },
      { key: "qr-box", label: "检出数量", children: NOT_INSPECTED },
      { key: "qr-payloads", label: "截断载荷", children: NOT_INSPECTED },
    ];
  }
  // missing、init_failed 和空串都不是 ready：检出写固定文案，数量和载荷写「本次未识别」
  if (qr.engine !== ENGINE_READY) {
    return [
      { key: "qr-engine", label: "引擎状态", children: engineSummaryText(qr.engine, qr.error) },
      ...qrLayerLines(qr),
      { key: "qr-found", label: "是否检出", children: QR_ENGINE_MISSING },
      { key: "qr-box", label: "检出数量", children: QR_COUNT_NOT_RECOGNIZED },
      { key: "qr-payloads", label: "截断载荷", children: QR_COUNT_NOT_RECOGNIZED },
    ];
  }
  // 载荷已由后端截断，页面原样展示，不再加工
  const payloads = qr.payloads && qr.payloads.length > 0 ? qr.payloads.join(" / ") : "无";
  return [
    { key: "qr-engine", label: "引擎状态", children: engineSummaryText(qr.engine, qr.error) },
    ...qrLayerLines(qr),
    { key: "qr-found", label: "是否检出", children: qr.found ? "已检出" : "未检出" },
    { key: "qr-layer", label: "命中层", children: layerText(qr.layer) },
    { key: "qr-box", label: "检出数量", children: String(qr.box_count || 0) },
    { key: "qr-payloads", label: "截断载荷", children: payloads },
  ];
}

// OCR 区要显示的几行。同样要区分没跑过、没加载和没认到字。
function ocrLines(ocr: ImageOcrDiagnosis): ResultLine[] {
  const engine = ocr.engine || "";
  // 预检没过时后端给空对象，本次没跑 OCR
  if (!engine) {
    return [
      { key: "ocr-engine", label: "引擎状态", children: NOT_INSPECTED },
      { key: "ocr-text", label: "OCR 文本", children: NOT_INSPECTED },
    ];
  }
  // 引擎没加载：文字这行写固定文案，不写成「无文字」
  if (engine !== ENGINE_READY) {
    return [
      { key: "ocr-engine", label: "引擎状态", children: engineText(engine, ocr.error) },
      { key: "ocr-text", label: "OCR 文本", children: OCR_ENGINE_MISSING },
    ];
  }
  return [
    { key: "ocr-engine", label: "引擎状态", children: engineText(engine, ocr.error) },
    { key: "ocr-text", label: "OCR 文本", children: ocr.text ? ocr.text : "无文字" },
  ];
}

// 模型那几行：命中的触发词、有没有真送模型、模型结论和说明
function modelLines(result: ImageTestResult): ResultLine[] {
  return [
    { key: "trigger", label: "触发词", children: result.trigger ? result.trigger : "无" },
    { key: "llm", label: "是否送模型", children: result.llm_called ? "是" : "否" },
    { key: "verdict", label: "模型结论", children: result.verdict ? result.verdict : "无" },
    { key: "reason", label: "模型说明", children: result.reason ? result.reason : "无" },
  ];
}

export function ForbiddenImageTestView() {
  const [dataUrl, setDataUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<ImageTestResult | null>(null);
  const [problem, setProblem] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // 桥接取不到时先报失败，避免选完图才发现调不了后端
    try {
      getBridge();
    } catch (error) {
      setProblem(readError(error));
    }
  }, []);

  // 读成 data URL：一份给 img 预览，一份直接当请求体的 image_base64
  function readPreview(file: File): void {
    const reader = new FileReader();
    reader.onload = () => {
      // 只有读到字符串才算成功，否则保持无预览，检测按钮也就点不了
      if (typeof reader.result === "string") {
        setDataUrl(reader.result);
        setFileName(file.name);
      } else {
        setProblem("图片读取失败，请重新选择。");
      }
    };
    reader.onerror = () => {
      setProblem("图片读取失败，请重新选择。");
    };
    reader.readAsDataURL(file);
  }

  // beforeUpload 一律回 false：文件不进上传队列，也不发任何请求
  function pickFile(file: File): boolean {
    const reason = checkImage(file);
    // 不合规：摆出原因并清掉上一次的预览，检测按钮随之不可用
    if (reason) {
      setProblem(reason);
      setDataUrl("");
      setFileName("");
      return false;
    }
    setProblem("");
    setResult(null);
    readPreview(file);
    return false;
  }

  async function runTest(): Promise<void> {
    setLoading(true);
    setProblem("");
    try {
      // 后端允许 data:image/...;base64, 前缀，整段送过去，页面不切字符串
      const inspected = await apiPost<ImageTestResult>("forbidden/image-test", {
        image_base64: dataUrl,
      });
      setResult(inspected);
    } catch (error) {
      setResult(null);
      setProblem("检测失败：" + readError(error));
    }
    setLoading(false);
  }

  // 没有预览或正在请求时都不让点，避免空体和重复请求
  const canTest = Boolean(dataUrl) && !loading;

  return (
    <Card title="图片检测测试">
      <p className="hint">
        结果来自三级本地解码（微信、zxing、QReader）和 RapidOCR。不会撤回、禁言、发飞书，也不写违禁日志。旧「违禁测试」页的二维码开关在本页不解码，本页的结论只认这张图。
      </p>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Upload
          accept="image/png,image/jpeg,image/webp,image/gif"
          maxCount={1}
          showUploadList={false}
          beforeUpload={pickFile}
        >
          <Button>选择图片</Button>
        </Upload>
        {/* 有预览才画图，同时带出文件名便于核对选的是哪张 */}
        {dataUrl ? <img className="test-pic" src={dataUrl} alt={fileName} /> : null}
        <Button type="primary" loading={loading} disabled={!canTest} onClick={runTest}>
          检测
        </Button>
        {/* 校验失败或请求失败都摆在这里 */}
        {problem ? <Alert type="error" message={problem} /> : null}
        {result ? (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Descriptions title="二维码" column={1} size="small" bordered items={qrLines(result.qr)} />
            <Descriptions title="OCR" column={1} size="small" bordered items={ocrLines(result.ocr)} />
            <Descriptions title="模型" column={1} size="small" bordered items={modelLines(result)} />
            {/* gif 的热路径差别由后端写在 note 里，有就展示 */}
            {result.note ? <Alert type="info" message={result.note} /> : null}
            <Alert type="info" message={<pre className="result">{result.message}</pre>} />
          </Space>
        ) : null}
      </Space>
    </Card>
  );
}
