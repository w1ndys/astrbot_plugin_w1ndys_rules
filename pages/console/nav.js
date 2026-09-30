// 页面层：本页顶栏。必须和 app.js 放在同一目录。
// 宿主只有 console 这一条路由。Tab 是页内面板，不是目录名。

export const PAGE_TABS = [
  { key: "settings", label: "全局配置" },
  { key: "keywords", label: "关键词" },
  { key: "forbidden-test", label: "违禁测试" },
  { key: "forbidden-logs", label: "违禁日志" },
];

export function currentPageId() {
  return "settings";
}

export function pageTabItems(views) {
  return PAGE_TABS.map((tab) => ({
    key: tab.key,
    label: tab.label,
    children: views[tab.key],
  }));
}
