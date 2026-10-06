// 页面层：违禁日志表。列表不展示原文，详情用 img 看图。
// 群名读已有的群名映射；群昵称是命中时存下的快照，旧日志可在页面上手动回补一次。
// 每一行可以按本群或全局加白 / 拉黑；本群只影响该群，全局影响所有群，拉黑不踢人。

import { useCallback, useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Drawer, Input, Pagination, Select, Space, Table, Typography } from "antd";
import type { TableProps } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type {
  BackfillResponse,
  ForbiddenLogDetail,
  ForbiddenLogListResponse,
  ForbiddenLogRow,
  GroupNameItem,
  GroupNameListResponse,
  LogPicture,
  RosterFlags,
  RosterResponse,
} from "./types";

// 原因下拉项：value 是后端认的 reason_code。
interface ReasonOption {
  value: string;
  label: string;
}

const REASON_OPTIONS: ReasonOption[] = [
  { value: "", label: "全部原因" },
  { value: "model", label: "文本模型" },
  { value: "group_card", label: "群名片" },
  { value: "qrcode", label: "二维码" },
  { value: "image_model", label: "图片转写" },
];

// 全局名单在库里的固定群号键，和后端 constants 一致。
const GLOBAL_SCOPE = "global";

// 四个接口路径，和后端 _register_log_pages 注册的地址一致。
// 键由「名单名 + _add / _remove」拼成，所以这里按字符串下标存。
const ROSTER_PATHS: Record<string, string> = {
  whitelist_add: "whitelist/add",
  whitelist_remove: "whitelist/remove",
  blacklist_add: "blacklist/add",
  blacklist_remove: "blacklist/remove",
};

// 名单按钮的两个维度：哪张名单、哪个范围。
type RosterKind = "whitelist" | "blacklist";
type RosterScope = "group" | "global";

// 名单按钮只用到四个状态和身份字段，列表行和详情都满足。
interface RosterTarget extends RosterFlags {
  id: number;
  group_id: string;
  user_id: string;
}

// 点按钮时的加名单 / 移名单回调。
type RosterToggle = (target: RosterTarget, kind: RosterKind, scope: RosterScope) => void;

// 三个筛选条件，applied 是点「筛选」后真正生效的那份。
interface LogFilter {
  group_id: string;
  user_id: string;
  reason_code: string;
}

// 列定义数组；TableProps 里的类型带 undefined，拼不起来，这里去掉
type LogColumns = NonNullable<TableProps<ForbiddenLogRow>["columns"]>;

function renderPictures(pictures: LogPicture[]) {
  const items = pictures || [];
  // 没有图就直接说明，不用给空列表
  if (!items.length) {
    return <p className="log-pic-fail">没有图片</p>;
  }
  return items.map((item, index) => {
    // 采集成功才有 src，直接用 src 出图
    if (item && item.ok && item.src) {
      return <img key={String(index)} className="log-pic" src={item.src} alt="命中时保存的图" />;
    }
    return (
      <p key={String(index)} className="log-pic-fail">
        图片未能保存
      </p>
    );
  });
}

function renderJson(value: unknown) {
  // 空值当成没有 JSON 段
  if (value === undefined || value === null || value === "") {
    return <p className="log-json">没有 JSON 段</p>;
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return <p className="log-json">{text}</p>;
}

// 四个名单按钮。查的是这一行自己的四个状态，点了就加或移。
function rosterActions(target: RosterTarget, busy: boolean, onToggle: RosterToggle) {
  return (
    <Space wrap>
      <Button size="small" disabled={busy} onClick={() => onToggle(target, "whitelist", "group")}>
        {target.whitelisted ? "移出本群白名单" : "加入本群白名单"}
      </Button>
      <Button size="small" disabled={busy} onClick={() => onToggle(target, "whitelist", GLOBAL_SCOPE)}>
        {target.global_whitelisted ? "移出全局白名单" : "加入全局白名单"}
      </Button>
      <Button size="small" danger disabled={busy} onClick={() => onToggle(target, "blacklist", "group")}>
        {target.group_blacklisted ? "移出本群黑名单" : "加入本群黑名单"}
      </Button>
      <Button size="small" danger disabled={busy} onClick={() => onToggle(target, "blacklist", GLOBAL_SCOPE)}>
        {target.global_blacklisted ? "移出全局黑名单" : "加入全局黑名单"}
      </Button>
    </Space>
  );
}
// 群名映射对照群号：没保存过的群显示空字符串，群号仍然照显示。
function itemsToNameMap(items: GroupNameItem[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const item of items || []) {
    const groupId = String(item.group_id || "").trim();
    // 空群号对不上日志行
    if (!groupId) {
      continue;
    }
    map[groupId] = String(item.group_name || "").trim();
  }
  return map;
}

export function ForbiddenLogsView() {
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
  const [groupId, setGroupId] = useState("");
  const [userId, setUserId] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [applied, setApplied] = useState<LogFilter>({
    group_id: "",
    user_id: "",
    reason_code: "",
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<ForbiddenLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<ForbiddenLogDetail | null>(null);
  // 正在请求的那一行，键是「群号:QQ」，避免重复点
  const [busyKey, setBusyKey] = useState("");
  // 群号到群名的映射，和欢迎语、关键词页读的是同一份
  const [names, setNames] = useState<Record<string, string>>({});

  const load = useCallback(
    async (nextPage: number, nextSize: number, filter: LogFilter) => {
      setLoading(true);
      try {
        const result = await apiPost<ForbiddenLogListResponse>("forbidden-log/list", {
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
        message.error(readError(error));
      }
      setLoading(false);
    },
    [message],
  );

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      // 没有官方桥接就读不出表
      try {
        getBridge();
      } catch (error) {
        message.error(readError(error));
        return;
      }
      // 卸载后不再写状态
      if (cancelled) {
        return;
      }
      try {
        const mapped = await apiPost<GroupNameListResponse>("group-name/list", {});
        // 切走后丢掉映射结果
        if (!cancelled) {
          setNames(itemsToNameMap(mapped.items));
        }
      } catch (error) {
        message.error(readError(error));
      }
      // 映射失败也要把日志表拉出来
      if (!cancelled) {
        await load(1, 20, { group_id: "", user_id: "", reason_code: "" });
      }
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [message, load]);

  async function openDetail(row: ForbiddenLogRow) {
    try {
      const result = await apiPost<ForbiddenLogDetail>("forbidden-log/get", { id: row.id });
      setDetail(result);
    } catch (error) {
      message.error(readError(error));
    }
  }

  // 加或移一个范围的名单。范围只按按钮决定，行号只用来带 QQ 和判断本群状态。
  async function toggleRoster(target: RosterTarget, kind: RosterKind, scope: RosterScope) {
    const field: keyof RosterFlags = scope === GLOBAL_SCOPE
      ? (kind === "whitelist" ? "global_whitelisted" : "global_blacklisted")
      : (kind === "whitelist" ? "whitelisted" : "group_blacklisted");
    const path = ROSTER_PATHS[kind + (target[field] ? "_remove" : "_add")];
    setBusyKey(target.group_id + ":" + target.user_id);
    try {
      const result = await apiPost<RosterResponse>(path, {
        group_id: scope === GLOBAL_SCOPE ? GLOBAL_SCOPE : target.group_id,
        user_id: target.user_id,
        source_group_id: target.group_id,
      });
      message.success(result && result.message ? result.message : "已更新名单。");
      await load(page, pageSize, applied);
      // 抽屉里正好是这一行时，四个状态跟着刷新
      if (detail && String(detail.id) === String(target.id)) {
        setDetail({
          ...detail,
          whitelisted: Boolean(result && result.whitelisted),
          global_whitelisted: Boolean(result && result.global_whitelisted),
          group_blacklisted: Boolean(result && result.group_blacklisted),
          global_blacklisted: Boolean(result && result.global_blacklisted),
        });
      }
    } catch (error) {
      message.error(readError(error));
    }
    setBusyKey("");
  }

  // 手动回补空群昵称：只填空值，数据来自当前群成员资料。页面加载时不自动跑。
  async function backfillNicknames() {
    try {
      const result = await apiPost<BackfillResponse>("forbidden-log/backfill-nicknames", {});
      message.success(result && result.message ? result.message : "已回补群昵称。");
      await load(page, pageSize, applied);
    } catch (error) {
      message.error(readError(error));
    }
  }

  const columns: LogColumns = [
    { title: "时间", dataIndex: "created_at", key: "created_at" },
    { title: "群号", dataIndex: "group_id", key: "group_id" },
    {
      title: "群名",
      key: "group_name",
      // 映射里没有这个群号就显示空，群号照显示
      render: (_value: unknown, row: ForbiddenLogRow) => names[String(row.group_id)] || "",
    },
    { title: "成员", dataIndex: "user_id", key: "user_id" },
    { title: "群昵称", dataIndex: "sender_name", key: "sender_name" },
    { title: "原因", dataIndex: "reason_text", key: "reason_text" },
    {
      title: "操作",
      key: "action",
      render: (_value: unknown, row: ForbiddenLogRow) => (
        <Space wrap>
          <Button type="link" onClick={() => openDetail(row)}>
            查看
          </Button>
          {rosterActions(row, busyKey === row.group_id + ":" + row.user_id, toggleRoster)}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card title="违禁日志">
        <p className="hint">命中后才记。列表不看原文，点开一条才加载文本、卡片和图。群名读群名映射，群昵称是命中时存下来的，旧日志可以用「回补群昵称」按当前群成员资料补一次。本群名单只对该群生效，全局名单对所有群生效，拉黑不踢人。飞书 webhook 不在这页。</p>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input style={{ width: 160 }} placeholder="群号" value={groupId} onChange={(event) => setGroupId(event.target.value)} />
          <Input style={{ width: 160 }} placeholder="成员 QQ" value={userId} onChange={(event) => setUserId(event.target.value)} />
          <Select style={{ width: 140 }} value={reasonCode} options={REASON_OPTIONS} onChange={(value) => setReasonCode(value)} />
          <Button
            onClick={() => {
              const filter = {
                group_id: groupId.trim(),
                user_id: userId.trim(),
                reason_code: reasonCode,
              };
              setApplied(filter);
              load(1, pageSize, filter);
            }}
          >
            筛选
          </Button>
          <Button onClick={backfillNicknames}>回补群昵称</Button>
        </Space>
        <Table rowKey={(row) => String(row.id)} columns={columns} dataSource={items} loading={loading} pagination={false} />
        <div className="pager">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger
            onChange={(nextPage, nextSize) => load(nextPage, nextSize, applied)}
          />
        </div>
      </Card>
      <Drawer title={detail ? "日志 #" + detail.id : "日志"} open={Boolean(detail)} width={480} onClose={() => setDetail(null)}>
        {detail ? (
          <div>
            <Typography.Paragraph>群：{detail.group_id}</Typography.Paragraph>
            <Typography.Paragraph>群名：{names[String(detail.group_id)] || ""}</Typography.Paragraph>
            <Typography.Paragraph>成员：{detail.user_id}</Typography.Paragraph>
            <Typography.Paragraph>群昵称：{detail.sender_name || ""}</Typography.Paragraph>
            <Typography.Paragraph>原因：{detail.reason_text}</Typography.Paragraph>
            <Typography.Paragraph>时间：{detail.created_at}</Typography.Paragraph>
            <Typography.Paragraph>文本：{detail.text || "（空）"}</Typography.Paragraph>
            <p className="hint">名单</p>
            {rosterActions(detail, busyKey === detail.group_id + ":" + detail.user_id, toggleRoster)}
            <p className="hint">JSON 段</p>
            {renderJson(detail.json)}
            <p className="hint">图片</p>
            {renderPictures(detail.pictures)}
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
