// 页面层：宿主只有 console 这一条路由。Tab 是页内面板。

// 页内 Tab 的一项：key 决定渲染哪块业务，label 是显示名。
export interface PageTab {
  key: string;
  label: string;
}

export const PAGE_TABS: PageTab[] = [
  { key: "settings", label: "全局配置" },
  { key: "welcome", label: "欢迎语" },
  { key: "keywords", label: "关键词" },
  { key: "forbidden-triggers", label: "违禁触发词" },
  { key: "forbidden-test", label: "违禁测试" },
  { key: "forbidden-image-test", label: "图片检测测试" },
];
