// 页面层：四块业务放在同一 iframe 里切 Tab。
// 点 Tab 只改本页 state，不改宿主 hash。不用 JSX。

import React, { useEffect, useMemo, useState } from "./vendor/react.js";
import { createRoot } from "./vendor/client.js";
import { ConfigProvider, Tabs, theme } from "./vendor/antd.js";
import { currentPageId, pageTabItems } from "./nav.js";
import { SettingsView } from "./settings-view.js";
import { KeywordsView } from "./keywords-view.js";
import { ForbiddenTestView } from "./forbidden-test-view.js";
import { ForbiddenLogsView } from "./forbidden-logs-view.js";

const h = React.createElement;

function readIsDark() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("theme") === "dark" || params.get("isDark") === "true") {
    return true;
  }
  if (params.get("theme") === "light" || params.get("isDark") === "false") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function App() {
  const [active, setActive] = useState(currentPageId());
  const isDark = useMemo(() => readIsDark(), []);
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm;

  useEffect(() => {
    document.body.classList.toggle("is-dark", isDark);
  }, [isDark]);

  const items = pageTabItems({
    settings: h(SettingsView),
    keywords: h(KeywordsView),
    "forbidden-test": h(ForbiddenTestView),
    "forbidden-logs": h(ForbiddenLogsView),
  });

  return h(
    ConfigProvider,
    { theme: { algorithm } },
    h(
      "main",
      { className: "page" },
      h(Tabs, {
        type: "card",
        size: "small",
        activeKey: active,
        onChange: setActive,
        destroyInactiveTabPane: true,
        items,
      }),
    ),
  );
}

const root = document.getElementById("app");
if (root) {
  createRoot(root).render(h(App));
}
