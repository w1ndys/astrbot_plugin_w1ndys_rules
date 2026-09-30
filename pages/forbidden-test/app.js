// 页面层：违禁词测试。React + Ant Design，经 AstrBot Pages 桥调后端。
// 组件从 CDN 拉，方便先看效果；离线 WebUI 打不开 CDN 时页面会空白。
// 不用 JSX：AstrBot 直接加载 module，没有 Babel。

import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Alert, Button, Card, ConfigProvider, Input, Select, Space, theme } from "antd";

const h = React.createElement;

// 跟 AstrBot 宿主主题，避免页面亮暗和外壳打架。
function readIsDark() {
  const params = new URLSearchParams(window.location.search);
  // AstrBot iframe 会带 theme=dark / light
  if (params.get("theme") === "dark" || params.get("isDark") === "true") {
    return true;
  }
  // 明确浅色时不要跟系统走
  if (params.get("theme") === "light" || params.get("isDark") === "false") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

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

// 测试页：输入文本、点测试、展示结果。
function App() {
  const [kind, setKind] = useState("text");
  const [qrFound, setQrFound] = useState(false);
  const [text, setText] = useState("");
  const [output, setOutput] = useState("还没测。");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const isDark = useMemo(() => readIsDark(), []);
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm;
  const bridge = window.AstrBotPluginPage;

  useEffect(() => {
    document.body.classList.toggle("is-dark", isDark);
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
  }, [bridge, isDark]);

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
    ConfigProvider,
    { theme: { algorithm } },
    h(
      "main",
      { className: "page" },
      h(
        Card,
        { title: "违禁词测试" },
        h(
          "p",
          { className: "hint" },
          "文本路要先命中触发词。图片转写走独立规则门。二维码试跑只认解码层检出。不会撤回、禁言或发飞书。",
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
      ),
    ),
  );
}

const root = document.getElementById("app");
// 没有挂载点就不要 createRoot，避免控制台报错
if (root) {
  createRoot(root).render(h(App));
}
