// 页面层：关键词表。React + Ant Design，经 AstrBot Pages 桥调后端。
// 不用 JSX：AstrBot 直接加载 module，没有 Babel。

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Button,
  Card,
  ConfigProvider,
  Input,
  Pagination,
  Space,
  Table,
  message,
  theme,
} from "antd";

const h = React.createElement;

// 跟 AstrBot 宿主主题，避免页面亮暗和外壳打架。
function readIsDark() {
  const params = new URLSearchParams(window.location.search);
  // AstrBot iframe 会带 theme=dark / light
  if (params.get("theme") === "dark" || params.get("isDark") === "true") {
    return true;
  }
  // 明确浅色时不要跟系统走
  if (params.get("theme") === "light" || params.get("isDark") === "false") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// 关键词表：筛选、分页、增删。
function App() {
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [groupId, setGroupId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [reply, setReply] = useState("");
  const isDark = useMemo(() => readIsDark(), []);
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm;
  const bridge = window.AstrBotPluginPage;

  const load = useCallback(
    async (nextPage, nextSize, groupFilter) => {
      setLoading(true);
      try {
        const result = await bridge.apiPost("keyword/list", {
          group_id: groupFilter,
          page: nextPage,
          page_size: nextSize,
        });
        setItems(result.items || []);
        setTotal(Number(result.total) || 0);
        setPage(Number(result.page) || nextPage);
        setPageSize(Number(result.page_size) || nextSize);
      } catch (error) {
        const text = error && error.message ? error.message : String(error);
        message.error(text);
      }
      setLoading(false);
    },
    [bridge],
  );

  useEffect(() => {
    document.body.classList.toggle("is-dark", isDark);
    let cancelled = false;
    async function boot() {
      // 普通脚本会在 SDK 注入前执行，必须等 bridge.ready
      if (!bridge) {
        message.error("页面桥接未就绪，请刷新后重试。");
        return;
      }
      await bridge.ready();
      // 页面已经卸了就不要再拉表
      if (cancelled) {
        return;
      }
      await load(1, 20, "");
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [bridge, isDark, load]);

  async function saveRow() {
    try {
      const result = await bridge.apiPost("keyword/save", {
        group_id: groupId,
        keyword,
        reply,
      });
      message.success(result.message || "已保存");
      await load(page, pageSize, applied);
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  async function deleteRow(row) {
    try {
      const result = await bridge.apiPost("keyword/delete", {
        group_id: row.group_id,
        keyword: row.keyword,
      });
      message.success(result.message || "已删除");
      await load(page, pageSize, applied);
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  const columns = [
    { title: "群号", dataIndex: "group_id", key: "group_id" },
    { title: "关键词", dataIndex: "keyword", key: "keyword" },
    { title: "回复", dataIndex: "reply", key: "reply" },
    {
      title: "操作",
      key: "action",
      render: (_, row) =>
        h(Button, { type: "link", danger: true, onClick: () => deleteRow(row) }, "删除"),
    },
  ];

  return h(
    ConfigProvider,
    { theme: { algorithm } },
    h(
      "main",
      { className: "page" },
      h(
        Card,
        { title: "关键词回复" },
        h(
          "p",
          { className: "hint" },
          "一张表管全部群。开启仍看 WebUI「开启关键词回复的群」。群里不再认「关键词 批量」。唤醒后的增删改查还在。",
        ),
        h(
          Space,
          { wrap: true, style: { marginBottom: 16 } },
          h(Input, {
            style: { width: 180 },
            placeholder: "按群号过滤，空则全部",
            value: filter,
            onChange: (event) => setFilter(event.target.value),
          }),
          h(
            Button,
            {
              onClick: () => {
                setApplied(filter.trim());
                load(1, pageSize, filter.trim());
              },
            },
            "筛选",
          ),
        ),
        h(
          Space,
          { wrap: true, style: { marginBottom: 16 } },
          h(Input, {
            style: { width: 140 },
            placeholder: "群号",
            value: groupId,
            onChange: (event) => setGroupId(event.target.value),
          }),
          h(Input, {
            style: { width: 160 },
            placeholder: "关键词",
            value: keyword,
            onChange: (event) => setKeyword(event.target.value),
          }),
          h(Input, {
            style: { width: 220 },
            placeholder: "回复",
            value: reply,
            onChange: (event) => setReply(event.target.value),
          }),
          h(Button, { type: "primary", onClick: saveRow }, "保存"),
        ),
        h(Table, {
          rowKey: (row) => row.group_id + "\0" + row.keyword,
          columns,
          dataSource: items,
          loading,
          pagination: false,
        }),
        h(
          "div",
          { className: "pager" },
          h(Pagination, {
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (nextPage, nextSize) => load(nextPage, nextSize, applied),
          }),
        ),
      ),
    ),
  );
}

const root = document.getElementById("app");
// 没有挂载点就不要 createRoot，避免控制台报错
if (root) {
  createRoot(root).render(h(App));
}
