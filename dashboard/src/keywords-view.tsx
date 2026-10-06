// 页面层：关键词表。一张表管全部群。

import { useCallback, useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Input, Pagination, Space, Table } from "antd";
import type { TableProps } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type {
  GroupNameItem,
  GroupNameListResponse,
  KeywordListResponse,
  KeywordRow,
  MessageResponse,
} from "./types";

// 列定义数组；TableProps 里的类型带 undefined，拼不起来，这里去掉
type KeywordColumns = NonNullable<TableProps<KeywordRow>["columns"]>;

function itemsToNameMap(items: GroupNameItem[]): Record<string, string> {
  // 映射表对照群号。没保存过的群显示空。
  const map: Record<string, string> = {};
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
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<KeywordRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const [groupId, setGroupId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [reply, setReply] = useState("");

  const load = useCallback(
    async (nextPage: number, nextSize: number, groupFilter: string) => {
      setLoading(true);
      try {
        const result = await apiPost<KeywordListResponse>("keyword/list", {
          group_id: groupFilter,
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
      // 映射失败也把关键词表拉出来
      if (!cancelled) {
        await load(1, 20, "");
      }
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [message, load]);

  async function saveRow() {
    try {
      const result = await apiPost<MessageResponse>("keyword/save", {
        group_id: groupId,
        keyword,
        reply,
      });
      message.success(result.message || "已保存");
      await load(page, pageSize, applied);
    } catch (error) {
      message.error(readError(error));
    }
  }

  async function deleteRow(row: KeywordRow) {
    try {
      const result = await apiPost<MessageResponse>("keyword/delete", {
        group_id: row.group_id,
        keyword: row.keyword,
      });
      message.success(result.message || "已删除");
      await load(page, pageSize, applied);
    } catch (error) {
      message.error(readError(error));
    }
  }

  const columns: KeywordColumns = [
    { title: "群号", dataIndex: "group_id", key: "group_id" },
    {
      title: "群名",
      key: "group_name",
      render: (_value: unknown, row: KeywordRow) => names[row.group_id] || "",
    },
    { title: "关键词", dataIndex: "keyword", key: "keyword" },
    { title: "回复", dataIndex: "reply", key: "reply" },
    {
      title: "操作",
      key: "action",
      render: (_value: unknown, row: KeywordRow) => (
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
