import { useEffect, useMemo, useState } from "react";
import { ConfigProvider, Tabs, theme } from "antd";
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
      <main className="page">
        <Tabs
          type="card"
          size="small"
          activeKey={active}
          onChange={setActive}
          destroyInactiveTabPane
          items={items}
        />
      </main>
    </ConfigProvider>
  );
}
