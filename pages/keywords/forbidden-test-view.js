// 页面层：违禁词测试面板。不会撤回、禁言或发飞书。

import React, { useEffect, useState } from "react";
import { Alert, Button, Card, Input, Select, Space } from "antd";

const h = React.createElement;

function formatResult(result) {
  const status = result && result.status ? String(result.status) : "";
  const trigger = result && result.trigger ? String(result.trigger) : "";
  const message =
    result && result.message ? String(result.message) : "没有返回说明。";
  const lines = [message];
  // 有触发词就单独列一行，方便对照配置
  if (trigger) {
    lines.push("触发词：" + trigger);
  }
  // status 给排障用，不是给群员看的
  if (status) {
    lines.push("状态：" + status);
  }
  return lines.join("\n");
}

export function ForbiddenTestView() {
  const [kind, setKind] = useState("text");
  const [qrFound, setQrFound] = useState(false);
  const [text, setText] = useState("");
  const [output, setOutput] = useState("还没测。");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const bridge = window.AstrBotPluginPage;

  useEffect(() => {
    let cancelled = false;
    async function waitBridge() {
      if (!bridge) {
        setFailed(true);
        setOutput("页面桥接未就绪，请刷新后重试。");
        return;
      }
      await bridge.ready();
      if (cancelled) {
        return;
      }
    }
    waitBridge();
    return () => {
      cancelled = true;
    };
  }, [bridge]);

  async function runTest() {
    setLoading(true);
    setFailed(false);
    setOutput("测试中…");
    try {
      const result = await bridge.apiPost("forbidden/test", {
        kind,
        text,
        qr_found: qrFound,
      });
      setOutput(formatResult(result));
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      setFailed(true);
      setOutput("测试失败：" + message);
    }
    setLoading(false);
  }

  return h(
    Card,
    { title: "违禁词测试" },
    h(
      "p",
      { className: "hint" },
      "文本路要先命中触发词。图片转写有可见文字就送模型，不走触发词。二维码试跑只认解码层检出。不会撤回、禁言或发飞书。",
    ),
    h(
      Space,
      { direction: "vertical", size: "large", style: { width: "100%" } },
      h(Select, {
        value: kind,
        options: [
          { value: "text", label: "文本" },
          { value: "transcript", label: "图片转写" },
          { value: "qr", label: "二维码检出" },
        ],
        onChange: (value) => setKind(value),
      }),
      h(Input.TextArea, {
        rows: 6,
        value: text,
        placeholder: "文本或图片转写贴这里",
        onChange: (event) => setText(event.target.value),
      }),
      h(
        Button,
        {
          onClick: () => setQrFound(!qrFound),
        },
        qrFound ? "二维码：已检出" : "二维码：未检出",
      ),
      h(
        Button,
        { type: "primary", loading, onClick: runTest },
        "测试",
      ),
      h(Alert, {
        type: failed ? "error" : "info",
        message: h("pre", { className: "result" }, output),
      }),
    ),
  );
}
