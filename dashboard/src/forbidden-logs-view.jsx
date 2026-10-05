// 页面层：违禁日志表。列表不展示原文，详情用 img 看图。
// 每一行可以按本群或全局加白 / 拉黑；本群只影响该群，全局影响所有群，拉黑不踢人。

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Drawer, Input, Pagination, Select, Space, Table, Typography, message } from "antd";

const REASON_OPTIONS = [
  { value: "", label: "全部原因" },
  { value: "model", label: "文本模型" },
  { value: "group_card", label: "群名片" },
  { value: "qrcode", label: "二维码" },
  { value: "image_model", label: "图片转写" },
];

// 全局名单在库里的固定群号键，和后端 constants 一致。
const GLOBAL_SCOPE = "global";

// 四个接口路径，和后端 _register_log_pages 注册的地址一致。
const ROSTER_PATHS = {
  whitelist_add: "whitelist/add",
  whitelist_remove: "whitelist/remove",
  blacklist_add: "blacklist/add",
  blacklist_remove: "blacklist/remove",
};

function renderPictures(pictures) {
  const items = pictures || [];
  if (!items.length) {
    return <p className="log-pic-fail">没有图片</p>;
  }
  return items.map((item, index) => {
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

function renderJson(value) {
  if (value === undefined || value === null || value === "") {
    return <p className="log-json">没有 JSON 段</p>;
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return <p className="log-json">{text}</p>;
}

// 四个名单按钮。查的是这一行自己的四个状态，点了就加或移。
function rosterActions(target, busy, onToggle) {
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

export function ForbiddenLogsView() {
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
  // 正在请求的那一行，键是「群号:QQ」，避免重复点
  const [busyKey, setBusyKey] = useState("");
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
  }, [bridge, load]);

  async function openDetail(row) {
    try {
      const result = await bridge.apiPost("forbidden-log/get", { id: row.id });
      setDetail(result);
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  // 加或移一个范围的名单。范围只按按钮决定，行号只用来带 QQ 和判断本群状态。
  async function toggleRoster(target, kind, scope) {
    const field = scope === GLOBAL_SCOPE
      ? (kind === "whitelist" ? "global_whitelisted" : "global_blacklisted")
      : (kind === "whitelist" ? "whitelisted" : "group_blacklisted");
    const path = ROSTER_PATHS[kind + (target[field] ? "_remove" : "_add")];
    setBusyKey(target.group_id + ":" + target.user_id);
    try {
      const result = await bridge.apiPost(path, {
        group_id: scope === GLOBAL_SCOPE ? GLOBAL_SCOPE : target.group_id,
        user_id: target.user_id,
        source_group_id: target.group_id,
      });
      message.success(result && result.message ? result.message : "已更新名单。");
      await load(page, pageSize, applied);
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
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
    setBusyKey("");
  }

  const columns = [
    { title: "时间", dataIndex: "created_at", key: "created_at" },
    { title: "群号", dataIndex: "group_id", key: "group_id" },
    { title: "成员", dataIndex: "user_id", key: "user_id" },
    { title: "原因", dataIndex: "reason_text", key: "reason_text" },
    {
      title: "操作",
      key: "action",
      render: (_, row) => (
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
        <p className="hint">命中后才记。列表不看原文，点开一条才加载文本、卡片和图。本群名单只对该群生效，全局名单对所有群生效，拉黑不踢人。飞书 webhook 不在这页。</p>
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
            <Typography.Paragraph>成员：{detail.user_id}</Typography.Paragraph>
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
