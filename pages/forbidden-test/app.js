const bridge = window.AstrBotPluginPage;
const groupIdBox = document.getElementById("group-id");
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
      group_id: groupIdBox.value,
      text: textBox.value,
    });
    show(formatResult(result));
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    show("测试失败：" + message);
  }
}

async function boot() {
  await bridge.ready();
  runButton.addEventListener("click", () => {
    runTest();
  });
}

boot();
