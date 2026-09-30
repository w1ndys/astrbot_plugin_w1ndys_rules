// 页面层：非密钥全局配置面板。飞书 webhook 不展示、不提交。

import React, { useEffect, useState } from "./vendor/react.js";
import { Button, Card, Form, Input, InputNumber, Select, message } from "./vendor/antd.js";

const h = React.createElement;

function groupSelect(name, label) {
  return h(Form.Item, { name, label }, h(Select, { mode: "tags", tokenSeparators: [",", " "] }));
}

export function SettingsView() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const bridge = window.AstrBotPluginPage;

  useEffect(() => {
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
      setLoading(true);
      try {
        const data = await bridge.apiPost("settings/get", {});
        if (!cancelled) {
          form.setFieldsValue(data);
        }
      } catch (error) {
        const text = error && error.message ? error.message : String(error);
        message.error(text);
      }
      setLoading(false);
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [bridge, form]);

  async function save() {
    const values = await form.validateFields();
    try {
      const result = await bridge.apiPost("settings/save", values);
      message.success(result.message || "已保存");
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  return h(
    Card,
    { title: "全局配置", loading },
    h(
      "p",
      { className: "hint" },
      "手写非密钥字段，保存写回 schema。飞书 webhook 只在 AstrBot 官方插件配置页改。",
    ),
    h(
      Form,
      { form, layout: "vertical" },
      groupSelect("keyword_groups", "开启关键词回复的群"),
      groupSelect("forbidden_groups", "开启违禁词的群"),
      groupSelect("welcome_groups", "开启欢迎语的群"),
      groupSelect("verify_groups", "开启入群验证的群"),
      groupSelect("invite_groups", "开启邀请树的群"),
      groupSelect("forbidden_block_group_card_groups", "拦截群名片的群"),
      h(Form.Item, { name: "welcome_text", label: "入群欢迎语文案（全局默认）" }, h(Input.TextArea, { rows: 3 })),
      h(Form.Item, { name: "forbidden_guideline", label: "违禁长什么样" }, h(Input)),
      h(Form.Item, { name: "forbidden_samples", label: "违禁样本" }, h(Input.TextArea, { rows: 6 })),
      h(Form.Item, { name: "forbidden_mute_seconds", label: "禁言秒数" }, h(InputNumber, { min: 0, style: { width: "100%" } })),
      h(Form.Item, { name: "forbidden_remind_text", label: "提醒文案" }, h(Input)),
      h(Form.Item, { name: "verify_mute_seconds", label: "入群验证禁言秒数" }, h(InputNumber, { min: 0, style: { width: "100%" } })),
      h(Button, { type: "primary", onClick: save }, "保存"),
    ),
  );
}
