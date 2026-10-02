// 页面层：关键词表。一张表管全部群。

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Input, Pagination, Space, Table, message } from "antd";

function itemsToNameMap(items) {
  // 映射表对照群号。没保存过的群显示空。
  const map = {};
  for (const item of items || []) {
    const groupId = String(item.group_id || "").trim();
    // 空群号对不上关键词行
    if (!groupId) {
      continue;
    }
    map[groupId] = String(item.group_name || "").trim();
  }
  return map;
}


export function KeywordsView() {
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [names, setNames] = useState({});
  const [groupId, setGroupId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [reply, setReply] = useState("");
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
    let cancelled = false;
    async function boot() {
      // 没有官方桥接就读不出表
      if (!bridge) {
        message.error("页面桥接未就绪，请刷新后重试。");
        return;
      }
      await bridge.ready();
      // 卸载后不再写状态
      if (cancelled) {
        return;
      }
      try {
        const mapped = await bridge.apiPost("group-name/list", {});
        // 切走后丢掉映射结果
        if (!cancelled) {
          setNames(itemsToNameMap(mapped.items));
        }
      } catch (error) {
        const text = error && error.message ? error.message : String(error);
        message.error(text);
      }
      // 映射失败也把关键词表拉出来
      if (!cancelled) {
        await load(1, 20, "");
      }
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [bridge, load]);

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
    {
      title: "群名",
      key: "group_name",
      render: (_, row) => names[row.group_id] || "",
    },
    { title: "关键词", dataIndex: "keyword", key: "keyword" },
    { title: "回复", dataIndex: "reply", key: "reply" },
    {
      title: "操作",
      key: "action",
      render: (_, row) => (
        <Button type="link" danger onClick={() => deleteRow(row)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Card title="关键词回复">
      <p className="hint">
        一张表管全部群。开启仍看全局配置里该群是否勾选关键词。群里不再认自然语言增删改查，也不认「关键词 批量」。
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
      <Space wrap style={{ marginBottom: 16 }}>
        <Input style={{ width: 140 }} placeholder="群号" value={groupId} onChange={(event) => setGroupId(event.target.value)} />
        <Input style={{ width: 160 }} placeholder="关键词" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        <Input style={{ width: 220 }} placeholder="回复" value={reply} onChange={(event) => setReply(event.target.value)} />
        <Button type="primary" onClick={saveRow}>
          保存
        </Button>
      </Space>
      <Table
        rowKey={(row) => row.group_id + "\0" + row.keyword}
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
