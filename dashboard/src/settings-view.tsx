// 页面层：全局配置。按群号一行勾选功能，保存仍 POST 各功能名单。

// 飞书 webhook 在本页用密码框改。


import { useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Checkbox, Form, Input, InputNumber, Space, Table } from "antd";
import type { Dispatch, SetStateAction } from "react";
import type { FormInstance, TableProps } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type {
  FeatureFlags,
  FeatureKey,
  FeatureLists,
  GroupNameItem,
  GroupNameListResponse,
  MessageResponse,
  SettingsPayload,
} from "./types";

// 六个功能名单：配置键和表头。
interface FeatureItem {
  key: FeatureKey;
  title: string;
}

const FEATURES: FeatureItem[] = [
  { key: "keyword_groups", title: "关键词" },
  { key: "forbidden_groups", title: "违禁词" },
  { key: "welcome_groups", title: "欢迎语" },
  { key: "verify_groups", title: "入群验证" },
  { key: "invite_groups", title: "邀请树" },
  { key: "forbidden_block_group_card_groups", title: "拦截群名片" },
];

// 表格一行：群号加六个功能开关。
type SettingsRow = FeatureFlags & { groupId: string };

// 列定义数组；TableProps 里的类型带 undefined，拼不起来，这里去掉
type SettingsColumns = NonNullable<TableProps<SettingsRow>["columns"]>;

// 表单只收非名单字段，名单走上面的表。
type SettingsFormValues = Omit<SettingsPayload, FeatureKey>;

// 群号到群名的草稿。
type NameMap = Record<string, string>;

// 只用到两个方法，避免深层导入 antd 的内部类型
interface Notice {
  success: (text: string) => void;
  error: (text: string) => void;
}

// 改某一格勾选、删掉一行。
type ToggleFeature = (groupId: string, key: FeatureKey, checked: boolean) => void;
type RemoveGroup = (groupId: string) => void;

function emptyFlags(): FeatureFlags {
  // 新建一行时六个功能都先关。
  return {
    keyword_groups: false,
    forbidden_groups: false,
    welcome_groups: false,
    verify_groups: false,
    invite_groups: false,
    forbidden_block_group_card_groups: false,
  };
}

function listsToRows(data: SettingsPayload): SettingsRow[] {
  // 把各功能名单转成按群号一行。
  const byGroup: Record<string, SettingsRow> = {};
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

function rowsToLists(rows: SettingsRow[]): FeatureLists {
  // 把勾选表转回各功能名单，供 settings/save。
  const lists: FeatureLists = {
    keyword_groups: [],
    forbidden_groups: [],
    welcome_groups: [],
    verify_groups: [],
    invite_groups: [],
    forbidden_block_group_card_groups: [],
  };
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

function itemsToNameMap(items: GroupNameItem[]): NameMap {
  // 接口 items 收成群号到群名，给表格对照。
  const map: NameMap = {};
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

function nameDraftItems(names: NameMap): GroupNameItem[] {
  // 草稿转保存请求。按群号排，方便对日志。
  const items: GroupNameItem[] = [];
  const ids = Object.keys(names).sort();
  for (const groupId of ids) {
    items.push({ group_id: groupId, group_name: names[groupId] || "" });
  }
  return items;
}

function makeColumns(onToggle: ToggleFeature, onRemove: RemoveGroup, names: NameMap): SettingsColumns {
  // 群号列 + 群名列 + 功能勾选列 + 删除。
  const columns: SettingsColumns = [
    { title: "群号", dataIndex: "groupId", key: "groupId" },
    {
      title: "群名",
      key: "groupName",
      render: (_value: unknown, row: SettingsRow) => names[row.groupId] || "",
    },
  ];
  for (const feature of FEATURES) {
    columns.push({
      title: feature.title,
      key: feature.key,
      render: (_value: unknown, row: SettingsRow) => (
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
    render: (_value: unknown, row: SettingsRow) => (
      <Button type="link" danger onClick={() => onRemove(row.groupId)}>
        删除
      </Button>
    ),
  });
  return columns;
}

function toggleRowFeature(
  setRows: Dispatch<SetStateAction<SettingsRow[]>>,
  groupId: string,
  key: FeatureKey,
  checked: boolean,
) {
  // 改某一群的某一个功能勾选。
  setRows((current) =>
    current.map((row) => {
      // 只改点到的那一行
      if (row.groupId !== groupId) {
        return row;
      }
      const next: SettingsRow = { ...row };
      next[key] = checked;
      return next;
    }),
  );
}

function removeRow(setRows: Dispatch<SetStateAction<SettingsRow[]>>, groupId: string) {
  // 从表里去掉这个群，保存后该群各功能都关。
  setRows((current) => current.filter((row) => row.groupId !== groupId));
}

function addRow(
  notice: Notice,
  rows: SettingsRow[],
  setRows: Dispatch<SetStateAction<SettingsRow[]>>,
  rawId: string,
  setRawId: (value: string) => void,
) {
  // 补一行空勾选。群号已存在则拒绝。
  const groupId = rawId.trim();
  // 没填群号就没法建行
  if (!groupId) {
    notice.error("先填群号。");
    return;
  }
  // 同一群只保留一行，避免勾选对不上
  if (rows.some((row) => row.groupId === groupId)) {
    notice.error("这个群已经在表里。");
    return;
  }
  const next = [...rows, { groupId, ...emptyFlags() }];
  next.sort((a, b) => a.groupId.localeCompare(b.groupId));
  setRows(next);
  setRawId("");
}

async function bootSettings(
  notice: Notice,
  form: FormInstance<SettingsFormValues>,
  setRows: Dispatch<SetStateAction<SettingsRow[]>>,
  setNames: Dispatch<SetStateAction<NameMap>>,
  setLoading: Dispatch<SetStateAction<boolean>>,
  cancelled: () => boolean,
) {
  // 进页拉配置和已保存群名。
  // 没有官方桥接就读不出配置
  try {
    getBridge();
  } catch (error) {
    notice.error(readError(error));
    return;
  }
  // 卸载后不再写状态
  if (cancelled()) {
    return;
  }
  setLoading(true);
  try {
    const data = await apiPost<SettingsPayload>("settings/get", {});
    // 慢请求回来时页面可能已经切走
    if (!cancelled()) {
      form.setFieldsValue(data);
      setRows(listsToRows(data));
    }
    const names = await apiPost<GroupNameListResponse>("group-name/list", {});
    // 映射失败不影响勾选表，上面已经摊好了
    if (!cancelled()) {
      setNames(itemsToNameMap(names.items));
    }
  } catch (error) {
    notice.error(readError(error));
  }
  setLoading(false);
}

async function saveSettings(notice: Notice, form: FormInstance<SettingsFormValues>, rows: SettingsRow[]) {
  // 勾选转名单，连同文案秒数一起 POST。不写群名。
  const values = await form.validateFields();
  const payload: SettingsPayload = { ...values, ...rowsToLists(rows) };
  try {
    const result = await apiPost<MessageResponse>("settings/save", payload);
    notice.success(result.message || "已保存");
  } catch (error) {
    notice.error(readError(error));
  }
}

async function pullGroupNames(
  notice: Notice,
  setNames: Dispatch<SetStateAction<NameMap>>,
  setBusy: Dispatch<SetStateAction<boolean>>,
) {
  // 调一次协议，只改草稿。
  setBusy(true);
  try {
    const data = await apiPost<GroupNameListResponse>("group-name/pull", {});
    const incoming = itemsToNameMap(data.items);
    setNames((current) => ({ ...current, ...incoming }));
    notice.success("已填入群名，尚未保存。");
  } catch (error) {
    notice.error(readError(error));
  }
  setBusy(false);
}

async function saveGroupNames(notice: Notice, names: NameMap) {
  // 把草稿 upsert 进映射表。
  try {
    const result = await apiPost<MessageResponse>("group-name/save", {
      items: nameDraftItems(names),
    });
    notice.success(result.message || "已保存群名");
  } catch (error) {
    notice.error(readError(error));
  }
}

// 群号表和添加框要用的状态与回调。
interface GroupTableProps {
  rows: SettingsRow[];
  setRows: Dispatch<SetStateAction<SettingsRow[]>>;
  columns: SettingsColumns;
  newGroupId: string;
  setNewGroupId: Dispatch<SetStateAction<string>>;
  nameBusy: boolean;
  onPullNames: () => void;
  onSaveNames: () => void;
}

function GroupTable(props: GroupTableProps) {
  // 群号表和添加框。
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
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
        <Button onClick={() => addRow(message, props.rows, props.setRows, props.newGroupId, props.setNewGroupId)}>
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

// 非名单字段的表单和保存按钮。
interface ExtraFieldsProps {
  form: FormInstance<SettingsFormValues>;
  onSave: () => void;
}

function ExtraFields(props: ExtraFieldsProps) {
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
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
  const [form] = Form.useForm<SettingsFormValues>();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<SettingsRow[]>([]);
  const [names, setNames] = useState<NameMap>({});
  const [nameBusy, setNameBusy] = useState(false);
  const [newGroupId, setNewGroupId] = useState("");

  useEffect(() => {
    let cancelled = false;
    bootSettings(message, form, setRows, setNames, setLoading, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [message, form]);

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
        onPullNames={() => pullGroupNames(message, setNames, setNameBusy)}
        onSaveNames={() => saveGroupNames(message, names)}
      />
      <ExtraFields form={form} onSave={() => saveSettings(message, form, rows)} />
    </Card>
  );
}
