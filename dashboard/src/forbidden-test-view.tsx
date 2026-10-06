// 页面层：违禁词测试面板。不会撤回、禁言或发飞书。

import { useEffect, useState } from "react";
import { Alert, Button, Card, Input, Select, Space } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type { ForbiddenTestResult } from "./types";

// 三种试跑模式：文本、图片转写、二维码检出。
type TestKind = "text" | "transcript" | "qr";

// 模式下拉项：value 是后端认的 kind。
interface TestKindOption {
  value: TestKind;
  label: string;
}

const TEST_KIND_OPTIONS: TestKindOption[] = [
  { value: "text", label: "文本" },
  { value: "transcript", label: "图片转写" },
  { value: "qr", label: "二维码检出" },
];

function formatResult(result: ForbiddenTestResult): string {
  const status = result && result.status ? String(result.status) : "";
  const trigger = result && result.trigger ? String(result.trigger) : "";
  const message = result && result.message ? String(result.message) : "没有返回说明。";
  const lines = [message];
  // 命中触发词才多一行触发词
  if (trigger) {
    lines.push("触发词：" + trigger);
  }
  // 后端给了状态才多一行状态
  if (status) {
    lines.push("状态：" + status);
  }
  return lines.join("\n");
}

export function ForbiddenTestView() {
  const [kind, setKind] = useState<TestKind>("text");
  const [qrFound, setQrFound] = useState(false);
  const [text, setText] = useState("");
  const [output, setOutput] = useState("还没测。");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // 桥接取不到时先报失败，文案与原来一致；ready() 由 apiPost 内部等
    try {
      getBridge();
    } catch (error) {
      setFailed(true);
      setOutput(readError(error));
    }
  }, []);

  async function runTest() {
    setLoading(true);
    setFailed(false);
    setOutput("测试中…");
    try {
      const result = await apiPost<ForbiddenTestResult>("forbidden/test", {
        kind,
        text,
        qr_found: qrFound,
      });
      setOutput(formatResult(result));
    } catch (error) {
      setFailed(true);
      setOutput("测试失败：" + readError(error));
    }
    setLoading(false);
  }

  return (
    <Card title="违禁词测试">
      <p className="hint">
        文本路要先命中触发词。图片转写有可见文字就送模型，不走触发词。二维码试跑只认解码层检出。不会撤回、禁言或发飞书。
      </p>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Select
          value={kind}
          options={TEST_KIND_OPTIONS}
          onChange={(value) => setKind(value)}
        />
        <Input.TextArea
          rows={6}
          value={text}
          placeholder="文本或图片转写贴这里"
          onChange={(event) => setText(event.target.value)}
        />
        <Button onClick={() => setQrFound(!qrFound)}>{qrFound ? "二维码：已检出" : "二维码：未检出"}</Button>
        <Button type="primary" loading={loading} onClick={runTest}>
          测试
        </Button>
        <Alert type={failed ? "error" : "info"} message={<pre className="result">{output}</pre>} />
      </Space>
    </Card>
  );
}
