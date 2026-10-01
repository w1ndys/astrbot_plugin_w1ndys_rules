// 页面层：每群一条欢迎语覆盖。空文案关闭本群，删除行继承全局。

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Input, Pagination, Space, Table, message } from "antd";

export function WelcomeView() {
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [groupId, setGroupId] = useState("");
  const [content, setContent] = useState("");
  const bridge = window.AstrBotPluginPage;

  const load = useCallback(
    async (nextPage, nextSize, groupFilter) => {
      setLoading(true);
      try {
        const result = await bridge.apiPost("welcome/list", {
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
      await load(1, 20, "");
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [bridge, load]);

  async function saveRow() {
    try {
      const result = await bridge.apiPost("welcome/save", {
        group_id: groupId,
        content,
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
      const result = await bridge.apiPost("welcome/delete", {
        group_id: row.group_id,
      });
      message.success(result.message || "已删除");
      await load(page, pageSize, applied);
    } catch (error) {
      const text = error && error.message ? error.message : String(error);
      message.error(text);
    }
  }

  const columns = [
    { title: "群号", dataIndex: "group_id", key: "group_id", width: 160 },
    {
      title: "欢迎语",
      dataIndex: "content",
      key: "content",
      render: (value) => (value ? value : "（空：本群关闭）"),
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_, row) => (
        <Button type="link" danger onClick={() => deleteRow(row)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Card title="入群欢迎语">
      <p className="hint">
        每群一条独立文案。保存空文案则本群关闭，优先于全局配置里的开启勾选。删除一行则改回继承全局默认。群里「欢迎语 设置」仍可用。
      </p>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          style={{ width: 180 }}
          placeholder="按群号过滤，空则全部"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <Button
          onClick={() => {
            setApplied(filter.trim());
            load(1, pageSize, filter.trim());
          }}
        >
          筛选
        </Button>
      </Space>
      <Space wrap style={{ marginBottom: 16 }} align="start">
        <Input
          style={{ width: 140 }}
          placeholder="群号"
          value={groupId}
          onChange={(event) => setGroupId(event.target.value)}
        />
        <Input.TextArea
          style={{ width: 360 }}
          rows={3}
          placeholder="欢迎语文案，留空则关闭本群"
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <Button type="primary" onClick={saveRow}>
          保存
        </Button>
      </Space>
      <Table
        rowKey={(row) => row.group_id}
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={false}
      />
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
  );
}
