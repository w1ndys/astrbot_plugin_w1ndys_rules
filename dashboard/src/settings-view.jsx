// 页面层：全局配置。按群号一行勾选功能，保存仍 POST 各功能名单。

// 飞书 webhook 在本页用密码框改。


import { useEffect, useState } from "react";
import { Button, Card, Checkbox, Form, Input, InputNumber, Space, Table, message } from "antd";

const FEATURES = [
  { key: "keyword_groups", title: "关键词" },
  { key: "forbidden_groups", title: "违禁词" },
  { key: "welcome_groups", title: "欢迎语" },
  { key: "verify_groups", title: "入群验证" },
  { key: "invite_groups", title: "邀请树" },
  { key: "forbidden_block_group_card_groups", title: "拦截群名片" },
];

function emptyFlags() {
  // 新建一行时六个功能都先关。
  const flags = {};
  for (const feature of FEATURES) {
    flags[feature.key] = false;
  }
  return flags;
}

function listsToRows(data) {
  // 把各功能名单转成按群号一行。
  const byGroup = {};
  for (const feature of FEATURES) {
    const groups = data[feature.key];
    // 名单不是数组就当这个功能全关
    if (!Array.isArray(groups)) {
      continue;
    }
    for (const raw of groups) {
      const groupId = String(raw).trim();
      // 空群号不能开功能
      if (!groupId) {
        continue;
      }
      // 第一次见到这个群就建一行，避免同一群号重复出现
      if (!byGroup[groupId]) {
        byGroup[groupId] = { groupId, ...emptyFlags() };
      }
      byGroup[groupId][feature.key] = true;
    }
  }
  return Object.keys(byGroup)
    .sort()
    .map((groupId) => byGroup[groupId]);
}

function rowsToLists(rows) {
  // 把勾选表转回各功能名单，供 settings/save。
  const lists = {};
  for (const feature of FEATURES) {
    lists[feature.key] = [];
  }
  for (const row of rows) {
    const groupId = String(row.groupId || "").trim();
    // 没填群号的空行不写进名单
    if (!groupId) {
      continue;
    }
    for (const feature of FEATURES) {
      // 勾了才进该功能名单
      if (row[feature.key]) {
        lists[feature.key].push(groupId);
      }
    }
  }
  return lists;
}

function itemsToNameMap(items) {
  // 接口 items 收成群号到群名，给表格对照。
  const map = {};
  for (const item of items || []) {
    const groupId = String(item.group_id || "").trim();
    // 空群号对不上勾选表
    if (!groupId) {
      continue;
    }
    map[groupId] = String(item.group_name || "").trim();
  }
  return map;
}

function nameDraftItems(names) {
  // 草稿转保存请求。按群号排，方便对日志。
  const items = [];
  const ids = Object.keys(names).sort();
  for (const groupId of ids) {
    items.push({ group_id: groupId, group_name: names[groupId] || "" });
  }
  return items;
}

function makeColumns(onToggle, onRemove, names) {
  // 群号列 + 群名列 + 功能勾选列 + 删除。
  const columns = [
    { title: "群号", dataIndex: "groupId", key: "groupId" },
    {
      title: "群名",
      key: "groupName",
      render: (_, row) => names[row.groupId] || "",
    },
  ];
  for (const feature of FEATURES) {
    columns.push({
      title: feature.title,
      key: feature.key,
      render: (_, row) => (
        <Checkbox
          checked={!!row[feature.key]}
          onChange={(event) => onToggle(row.groupId, feature.key, event.target.checked)}
        />
      ),
    });
  }
  columns.push({
    title: "操作",
    key: "action",
    render: (_, row) => (
      <Button type="link" danger onClick={() => onRemove(row.groupId)}>
        删除
      </Button>
    ),
  });
  return columns;
}

function toggleRowFeature(setRows, groupId, key, checked) {
  // 改某一群的某一个功能勾选。
  setRows((current) =>
    current.map((row) => {
      // 只改点到的那一行
      if (row.groupId !== groupId) {
        return row;
      }
      return { ...row, [key]: checked };
    }),
  );
}

function removeRow(setRows, groupId) {
  // 从表里去掉这个群，保存后该群各功能都关。
  setRows((current) => current.filter((row) => row.groupId !== groupId));
}

function addRow(rows, setRows, rawId, setRawId) {
  // 补一行空勾选。群号已存在则拒绝。
  const groupId = rawId.trim();
  // 没填群号就没法建行
  if (!groupId) {
    message.error("先填群号。");
    return;
  }
  // 同一群只保留一行，避免勾选对不上
  if (rows.some((row) => row.groupId === groupId)) {
    message.error("这个群已经在表里。");
    return;
  }
  const next = [...rows, { groupId, ...emptyFlags() }];
  next.sort((a, b) => a.groupId.localeCompare(b.groupId));
  setRows(next);
  setRawId("");
}

async function bootSettings(bridge, form, setRows, setNames, setLoading, cancelled) {
  // 进页拉配置和已保存群名。
  // 没有官方桥接就读不出配置
  if (!bridge) {
    message.error("页面桥接未就绪，请刷新后重试。");
    return;
  }
  await bridge.ready();
  // 卸载后不再写状态
  if (cancelled()) {
    return;
  }
  setLoading(true);
  try {
    const data = await bridge.apiPost("settings/get", {});
    // 慢请求回来时页面可能已经切走
    if (!cancelled()) {
      form.setFieldsValue(data);
      setRows(listsToRows(data));
    }
    const names = await bridge.apiPost("group-name/list", {});
    // 映射失败不影响勾选表，上面已经摊好了
    if (!cancelled()) {
      setNames(itemsToNameMap(names.items));
    }
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    message.error(text);
  }
  setLoading(false);
}

async function saveSettings(bridge, form, rows) {
  // 勾选转名单，连同文案秒数一起 POST。不写群名。
  const values = await form.validateFields();
  const payload = { ...values, ...rowsToLists(rows) };
  try {
    const result = await bridge.apiPost("settings/save", payload);
    message.success(result.message || "已保存");
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    message.error(text);
  }
}

async function pullGroupNames(bridge, setNames, setBusy) {
  // 调一次协议，只改草稿。
  setBusy(true);
  try {
    const data = await bridge.apiPost("group-name/pull", {});
    const incoming = itemsToNameMap(data.items);
    setNames((current) => ({ ...current, ...incoming }));
    message.success("已填入群名，尚未保存。");
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    message.error(text);
  }
  setBusy(false);
}

async function saveGroupNames(bridge, names) {
  // 把草稿 upsert 进映射表。
  try {
    const result = await bridge.apiPost("group-name/save", {
      items: nameDraftItems(names),
    });
    message.success(result.message || "已保存群名");
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    message.error(text);
  }
}

function GroupTable(props) {
  // 群号表和添加框。
  return (
    <>
      <p className="hint">
        按群号一行勾选要开的功能，保存写成各功能名单。没出现的群就是全关。飞书 webhook 也在本页改。群名只展示；点「拉取群名」填草稿，「保存群名」才写入映射表。欢迎语和关键词页读同一张表。
      </p>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          style={{ width: 220 }}
          placeholder="输入群号后点添加"
          value={props.newGroupId}
          onChange={(event) => props.setNewGroupId(event.target.value)}
        />
        <Button onClick={() => addRow(props.rows, props.setRows, props.newGroupId, props.setNewGroupId)}>
          添加群
        </Button>
        <Button loading={props.nameBusy} onClick={props.onPullNames}>
          拉取群名
        </Button>
        <Button onClick={props.onSaveNames}>保存群名</Button>
      </Space>
      <Table
        rowKey="groupId"
        size="small"
        pagination={false}
        columns={props.columns}
        dataSource={props.rows}
        style={{ marginBottom: 16 }}
        scroll={{ x: true }}
      />
    </>
  );
}

function ExtraFields(props) {
  // 欢迎语、违禁、验证秒数等非名单字段。
  return (
    <Form form={props.form} layout="vertical">
      <Form.Item name="welcome_text" label="入群欢迎语文案（全局默认）">
        <Input.TextArea rows={3} />
      </Form.Item>
      <Form.Item name="forbidden_guideline" label="违禁长什么样">
        <Input />
      </Form.Item>
      <Form.Item name="forbidden_samples" label="违禁样本">
        <Input.TextArea rows={6} />
      </Form.Item>
      <Form.Item name="forbidden_trigger_url" label="网址当触发词" valuePropName="checked">
        <Checkbox>消息里出现网址就送模型</Checkbox>
      </Form.Item>
      <Form.Item name="forbidden_trigger_group" label="群号当触发词" valuePropName="checked">
        <Checkbox>消息里出现加群/群号就送模型</Checkbox>
      </Form.Item>
      <Form.Item name="forbidden_trigger_qq" label="QQ 号当触发词" valuePropName="checked">
        <Checkbox>消息里出现 QQ 号就送模型</Checkbox>
      </Form.Item>
      <Form.Item name="forbidden_trigger_phone" label="手机号当触发词" valuePropName="checked">
        <Checkbox>消息里出现手机号就送模型</Checkbox>
      </Form.Item>
      <Form.Item name="forbidden_trigger_wechat" label="微信号当触发词" valuePropName="checked">
        <Checkbox>消息里出现微信号就送模型</Checkbox>
      </Form.Item>
      <Form.Item name="forbidden_mute_seconds" label="禁言秒数">
        <InputNumber min={0} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="forbidden_remind_text" label="提醒文案">
        <Input />
      </Form.Item>
      <Form.Item name="verify_mute_seconds" label="入群验证禁言秒数">
        <InputNumber min={0} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="forbidden_feishu_webhook" label="飞书 webhook">
        <Input.Password />
      </Form.Item>



      <Button type="primary" onClick={props.onSave}>
        保存
      </Button>
    </Form>
  );
}

export function SettingsView() {
  // 全局配置面板：表管功能开关，表单管文案秒数，群名单独拉和存。
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState([]);
  const [names, setNames] = useState({});
  const [nameBusy, setNameBusy] = useState(false);
  const [newGroupId, setNewGroupId] = useState("");
  const bridge = window.AstrBotPluginPage;

  useEffect(() => {
    let cancelled = false;
    bootSettings(bridge, form, setRows, setNames, setLoading, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [bridge, form]);

  const columns = makeColumns(
    (groupId, key, checked) => toggleRowFeature(setRows, groupId, key, checked),
    (groupId) => removeRow(setRows, groupId),
    names,
  );

  return (
    <Card title="全局配置" loading={loading}>
      <GroupTable
        rows={rows}
        setRows={setRows}
        newGroupId={newGroupId}
        setNewGroupId={setNewGroupId}
        columns={columns}
        nameBusy={nameBusy}
        onPullNames={() => pullGroupNames(bridge, setNames, setNameBusy)}
        onSaveNames={() => saveGroupNames(bridge, names)}
      />
      <ExtraFields form={form} onSave={() => saveSettings(bridge, form, rows)} />
    </Card>
  );
}
