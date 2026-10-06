import { createRoot } from "react-dom/client";
import { StyleProvider } from "@ant-design/cssinjs";
import App from "./App.jsx";
import "./style.css";

const root = document.getElementById("root");
if (root) {
  // layer 让 antd 的样式进 @layer antd：页面自己的无 layer CSS 在任何顺序下都压过它，
  // 覆盖交互态不用再堆权重或写 !important。StyleProvider 要在 ConfigProvider 外层，
  // 后者在 App 里。
  createRoot(root).render(
    <StyleProvider layer>
      <App />
    </StyleProvider>
  );
}
