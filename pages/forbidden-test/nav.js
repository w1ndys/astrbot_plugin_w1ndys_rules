// 页面层：本页顶栏。必须和 app.js 放在同一目录。
// AstrBot iframe 拦了顶层跳转。Tab 只在本页切面板。
// 不给每个 Tab 单独写宿主路由：token 按页签发，跨页会 401。

export const PAGE_TABS = [
  { key: "settings", label: "全局配置" },
  { key: "keywords", label: "关键词" },
  { key: "forbidden-test", label: "违禁测试" },
  { key: "forbidden-logs", label: "违禁日志" },
];

export function currentPageId() {
  const path = window.location.pathname.replace(/\/+$/, "");
  const parts = path.split("/");
  const last = parts[parts.length - 1] || "";
  // 打开的是 index.html 时，目录名才是页 id
  const fromPath = last === "index.html" ? parts[parts.length - 2] || "" : last;
  if (PAGE_TABS.some((tab) => tab.key === fromPath)) {
    return fromPath;
  }
  return "settings";
}

export function pageTabItems(views) {
  return PAGE_TABS.map((tab) => ({
    key: tab.key,
    label: tab.label,
    children: views[tab.key],
  }));
}
