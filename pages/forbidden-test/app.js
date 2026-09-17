const bridge = window.AstrBotPluginPage;
const textBox = document.getElementById("text");
const runButton = document.getElementById("run");
const output = document.getElementById("output");

function show(message) {
  output.textContent = message;
}

function formatResult(result) {
  const status = result && result.status ? String(result.status) : "";
  const trigger = result && result.trigger ? String(result.trigger) : "";
  const message = result && result.message ? String(result.message) : "没有返回说明。";
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

async function runTest() {
  show("测试中…");
  try {
    const result = await bridge.apiPost("forbidden/test", {
      text: textBox.value,
    });
    show(formatResult(result));
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    show("测试失败：" + message);
  }
}

async function boot() {
  // 普通脚本会在 AstrBot 注入的 bridge SDK 之前执行，必须用 module 等到 SDK 就绪。
  if (!bridge) {
    show("页面桥接未就绪，请刷新后重试。");
    return;
  }
  await bridge.ready();
  runButton.addEventListener("click", () => {
    runTest();
  });
}

boot();
