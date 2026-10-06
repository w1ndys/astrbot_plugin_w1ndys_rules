// 页面层：插件页外壳。六块业务放进页内 Tab，切换只改 React state，不动顶层 hash。

import { useEffect, useMemo, useState } from "react";
import { App as AntdApp, ConfigProvider, Tabs, theme } from "antd";
import { PAGE_TABS } from "./nav.js";
import { SettingsView } from "./settings-view.jsx";
import { WelcomeView } from "./welcome-view.jsx";
import { KeywordsView } from "./keywords-view.jsx";
import { ForbiddenTriggersView } from "./forbidden-triggers-view.jsx";
import { ForbiddenTestView } from "./forbidden-test-view.jsx";
import { ForbiddenLogsView } from "./forbidden-logs-view.jsx";

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

export default function App() {
  const [active, setActive] = useState("settings");
  const isDark = useMemo(() => readIsDark(), []);
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm;

  useEffect(() => {
    document.body.classList.toggle("is-dark", isDark);
  }, [isDark]);

  const items = PAGE_TABS.map((tab) => {
    let children = null;
    if (tab.key === "settings") {
      children = <SettingsView />;
    } else if (tab.key === "welcome") {
      children = <WelcomeView />;
    } else if (tab.key === "keywords") {
      children = <KeywordsView />;
    } else if (tab.key === "forbidden-triggers") {
      children = <ForbiddenTriggersView />;
    } else if (tab.key === "forbidden-test") {
      children = <ForbiddenTestView />;
    } else if (tab.key === "forbidden-logs") {
      children = <ForbiddenLogsView />;
    }
    return { key: tab.key, label: tab.label, children };
  });

  return (
    <ConfigProvider theme={{ algorithm }}>
      {/* 里面的 message 走 useApp 才会跟随宿主明暗主题；component={false} 少一层 div */}
      <AntdApp component={false}>
        <main className="page">
          <Tabs
            type="card"
            size="small"
            activeKey={active}
            onChange={setActive}
            destroyOnHidden
            items={items}
          />
        </main>
      </AntdApp>
    </ConfigProvider>
  );
}
