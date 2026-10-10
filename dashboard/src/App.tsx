// 页面层：插件页外壳。七块业务放进页内 Tab，切换只改 React state，不动顶层 hash。

import { useEffect, useMemo, useState } from "react";
import { App as AntdApp, ConfigProvider, Tabs, theme } from "antd";
import { PAGE_TABS } from "./nav";
import { SettingsView } from "./settings-view";
import { WelcomeView } from "./welcome-view";
import { KeywordsView } from "./keywords-view";
import { ForbiddenTriggersView } from "./forbidden-triggers-view";
import { ForbiddenTestView } from "./forbidden-test-view";
import { ForbiddenImageTestView } from "./forbidden-image-test-view";
import { ForbiddenLogsView } from "./forbidden-logs-view";

function readIsDark(): boolean {
  // 宿主把主题放进 query；没给就跟随系统
  const params = new URLSearchParams(window.location.search);
  // 明确给了暗色就按暗色
  if (params.get("theme") === "dark" || params.get("isDark") === "true") {
    return true;
  }
  // 明确给了亮色就按亮色
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
    // 一个 key 对应一块业务，切走的面板销毁，避免带着旧值回显
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
    } else if (tab.key === "forbidden-image-test") {
      children = <ForbiddenImageTestView />;
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
