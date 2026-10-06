import { createRoot } from "react-dom/client";
import { StyleProvider } from "@ant-design/cssinjs";
import App from "./App";
import "./style.css";

const root = document.getElementById("root");
// 容器不存在就没地方挂载，整页不渲染
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
