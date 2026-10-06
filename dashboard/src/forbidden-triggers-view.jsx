// 页面层：全局违禁触发词表。文本路命中这些词才送模型。

import { useCallback, useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Input, Pagination, Space, Table } from "antd";

async function loadRows(notice, bridge, nextPage, nextSize, query, setters) {
  // 拉一页触发词。
  setters.setLoading(true);
  try {
    const result = await bridge.apiPost("forbidden-trigger/list", {
      q: query,
      page: nextPage,
      page_size: nextSize,
    });
    setters.setItems(result.items || []);
    setters.setTotal(Number(result.total) || 0);
    setters.setPage(Number(result.page) || nextPage);
    setters.setPageSize(Number(result.page_size) || nextSize);
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    notice.error(text);
  }
  setters.setLoading(false);
}

async function saveRow(notice, bridge, content, oldContent, reload) {
  // 有旧词就改，没有就新增。
  try {
    const result = await bridge.apiPost("forbidden-trigger/save", {
      content,
      old_content: oldContent,
    });
    notice.success(result.message || "已保存");
    await reload();
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    notice.error(text);
  }
}

async function deleteRow(notice, bridge, content, reload) {
  // 按完整触发词删除。
  try {
    const result = await bridge.apiPost("forbidden-trigger/delete", {
      content,
    });
    notice.success(result.message || "已删除");
    await reload();
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    notice.error(text);
  }
}

export function ForbiddenTriggersView() {
  // 全局触发词增删改查。
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState("");
  const [oldContent, setOldContent] = useState("");
  const bridge = window.AstrBotPluginPage;
  const setters = { setItems, setTotal, setPage, setPageSize, setLoading };

  const load = useCallback(
    (nextPage, nextSize, query) => loadRows(message, bridge, nextPage, nextSize, query, setters),
    [bridge],
  );

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      // 没有官方桥接就读不出表
      if (!bridge) {
        message.error("页面桥接未就绪，请刷新后重试。");
        return;
      }
      await bridge.ready();
      // 卸载后不再拉表
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

  function reload() {
    return load(page, pageSize, applied);
  }

  const columns = [
    { title: "触发词", dataIndex: "content", key: "content" },
    {
      title: "操作",
      key: "action",
      render: (_, row) => (
        <Space>
          <Button
            type="link"
            onClick={() => {
              setOldContent(row.content);
              setContent(row.content);
            }}
          >
            编辑
          </Button>
          <Button type="link" danger onClick={() => deleteRow(message, bridge, row.content, reload)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Card title="违禁触发词">
      <p className="hint">
        全局共用。文本路要先命中这里的词才送模型。图片 OCR 有字仍不走触发词。增删改查只走本页。
      </p>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          style={{ width: 220 }}
          placeholder="按内容过滤，空则全部"
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
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          style={{ width: 320 }}
          placeholder={oldContent ? "改成这条触发词" : "新增触发词"}
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <Button
          type="primary"
          onClick={async () => {
            await saveRow(message, bridge, content, oldContent, reload);
            setOldContent("");
            setContent("");
          }}
        >
          {oldContent ? "保存修改" : "添加"}
        </Button>
        <Button
          onClick={() => {
            setOldContent("");
            setContent("");
          }}
        >
          取消编辑
        </Button>
      </Space>
      <Table
        rowKey="content"
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
