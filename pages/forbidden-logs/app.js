// 页面层：违禁日志只读表。React + Ant Design，经 AstrBot Pages 桥调后端。
// 不用 JSX：AstrBot 直接加载 module，没有 Babel。
// 列表不展示原文。详情用 img 看图，失败只写「图片未能保存」。

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Button,
  Card,
  ConfigProvider,
  Drawer,
  Input,
  Pagination,
  Select,
  Space,
  Table,
  Typography,
  message,
  theme,
} from "antd";

const h = React.createElement;

const REASON_OPTIONS = [
  { value: "", label: "全部原因" },
  { value: "model", label: "文本模型" },
  { value: "group_card", label: "群名片" },
  { value: "qrcode", label: "二维码" },
  { value: "image_model", label: "图片转写" },
];

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

function renderPictures(pictures) {
  const items = pictures || [];
  if (!items.length) {
    return h("p", { className: "log-pic-fail" }, "没有图片");
  }
  return items.map((item, index) => {
    if (item && item.ok && item.src) {
      return h("img", {
        key: String(index),
        className: "log-pic",
        src: item.src,
        alt: "命中时保存的图",
      });
    }
    return h(
      "p",
      { key: String(index), className: "log-pic-fail" },
      "图片未能保存",
    );
  });
}

function renderJson(value) {
  if (value === undefined || value === null || value === "") {
    return h("p", { className: "log-json" }, "没有 JSON 段");
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return h("p", { className: "log-json" }, text);
}

function App() {
  const [groupId, setGroupId] = useState("");
  const [userId, setUserId] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [applied, setApplied] = useState({
    group_id: "",
    user_id: "",
    reason_code: "",
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const isDark = useMemo(() => readIsDark(), []);
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm;
  const bridge = window.AstrBotPluginPage;

  const load = useCallback(
    async (nextPage, nextSize, filter) => {
      setLoading(true);
      try {
        const result = await bridge.apiPost("forbidden-log/list", {
          group_id: filter.group_id,
          user_id: filter.user_id,
          reason_code: filter.reason_code,
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
      if (!bridge) {
        message.error("页面桥接未就绪，请刷新后重试。");
        return;
      }
      await bridge.ready();
      if (cancelled) {
        return;
      }
      await load(1, 20, { group_id: "", user_id: "", reason_code: "" });
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [bridge, isDark, load]);

  async function openDetail(row) {
    try {
      const result = await bridge.apiPost("forbidden-log/get", { id: row.id });
      setDetail(result);
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  const columns = [
    { title: "时间", dataIndex: "created_at", key: "created_at" },
    { title: "群号", dataIndex: "group_id", key: "group_id" },
    { title: "成员", dataIndex: "user_id", key: "user_id" },
    { title: "原因", dataIndex: "reason_text", key: "reason_text" },
    {
      title: "操作",
      key: "action",
      render: (_, row) =>
        h(Button, { type: "link", onClick: () => openDetail(row) }, "查看"),
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
        { title: "违禁日志" },
        h(
          "p",
          { className: "hint" },
          "只读。命中后才记。列表不看原文，点开一条才加载文本、卡片和图。飞书 webhook 不在这页。",
        ),
        h(
          Space,
          { wrap: true, style: { marginBottom: 16 } },
          h(Input, {
            style: { width: 160 },
            placeholder: "群号",
            value: groupId,
            onChange: (event) => setGroupId(event.target.value),
          }),
          h(Input, {
            style: { width: 160 },
            placeholder: "成员 QQ",
            value: userId,
            onChange: (event) => setUserId(event.target.value),
          }),
          h(Select, {
            style: { width: 140 },
            value: reasonCode,
            options: REASON_OPTIONS,
            onChange: (value) => setReasonCode(value),
          }),
          h(
            Button,
            {
              onClick: () => {
                const filter = {
                  group_id: groupId.trim(),
                  user_id: userId.trim(),
                  reason_code: reasonCode,
                };
                setApplied(filter);
                load(1, pageSize, filter);
              },
            },
            "筛选",
          ),
        ),
        h(Table, {
          rowKey: (row) => String(row.id),
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
      h(
        Drawer,
        {
          title: detail ? "日志 #" + detail.id : "日志",
          open: Boolean(detail),
          width: 480,
          onClose: () => setDetail(null),
        },
        detail
          ? h(
              "div",
              null,
              h(Typography.Paragraph, null, "群：" + detail.group_id),
              h(Typography.Paragraph, null, "成员：" + detail.user_id),
              h(Typography.Paragraph, null, "原因：" + detail.reason_text),
              h(Typography.Paragraph, null, "时间：" + detail.created_at),
              h(Typography.Paragraph, null, "文本：" + (detail.text || "（空）")),
              h("p", { className: "hint" }, "JSON 段"),
              renderJson(detail.json),
              h("p", { className: "hint" }, "图片"),
              renderPictures(detail.pictures),
            )
          : null,
      ),
    ),
  );
}

const root = document.getElementById("app");
if (root) {
  createRoot(root).render(h(App));
}
