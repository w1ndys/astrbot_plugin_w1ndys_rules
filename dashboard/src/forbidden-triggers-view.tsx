// 页面层：全局违禁触发词表。文本路命中这些词才送模型。

import { useCallback, useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Input, Pagination, Space, Table } from "antd";
import type { Dispatch, SetStateAction } from "react";
import type { TableProps } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type {
  ForbiddenTriggerListResponse,
  ForbiddenTriggerRow,
  MessageResponse,
} from "./types";

// 只用到两个方法，避免深层导入 antd 的内部类型
interface Notice {
  success: (text: string) => void;
  error: (text: string) => void;
}

// 拉一页要写的几个状态
interface TriggerSetters {
  setItems: Dispatch<SetStateAction<ForbiddenTriggerRow[]>>;
  setTotal: Dispatch<SetStateAction<number>>;
  setPage: Dispatch<SetStateAction<number>>;
  setPageSize: Dispatch<SetStateAction<number>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
}

// 列定义数组；TableProps 里的类型带 undefined，拼不起来，这里去掉
type TriggerColumns = NonNullable<TableProps<ForbiddenTriggerRow>["columns"]>;

async function loadRows(notice: Notice, nextPage: number, nextSize: number, query: string, setters: TriggerSetters) {
  // 拉一页触发词。
  setters.setLoading(true);
  try {
    const result = await apiPost<ForbiddenTriggerListResponse>("forbidden-trigger/list", {
      q: query,
      page: nextPage,
      page_size: nextSize,
    });
    setters.setItems(result.items || []);
    setters.setTotal(Number(result.total) || 0);
    setters.setPage(Number(result.page) || nextPage);
    setters.setPageSize(Number(result.page_size) || nextSize);
  } catch (error) {
    notice.error(readError(error));
  }
  setters.setLoading(false);
}

async function saveRow(notice: Notice, content: string, oldContent: string, reload: () => Promise<void>) {
  // 有旧词就改，没有就新增。
  try {
    const result = await apiPost<MessageResponse>("forbidden-trigger/save", {
      content,
      old_content: oldContent,
    });
    notice.success(result.message || "已保存");
    await reload();
  } catch (error) {
    notice.error(readError(error));
  }
}

async function deleteRow(notice: Notice, content: string, reload: () => Promise<void>) {
  // 按完整触发词删除。
  try {
    const result = await apiPost<MessageResponse>("forbidden-trigger/delete", {
      content,
    });
    notice.success(result.message || "已删除");
    await reload();
  } catch (error) {
    notice.error(readError(error));
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
  const [items, setItems] = useState<ForbiddenTriggerRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState("");
  const [oldContent, setOldContent] = useState("");
  const setters = { setItems, setTotal, setPage, setPageSize, setLoading };

  const load = useCallback(
    (nextPage: number, nextSize: number, query: string) => loadRows(message, nextPage, nextSize, query, setters),
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
  }, [message, load]);

  function reload() {
    return load(page, pageSize, applied);
  }

  const columns: TriggerColumns = [
    { title: "触发词", dataIndex: "content", key: "content" },
    {
      title: "操作",
      key: "action",
      render: (_value: unknown, row: ForbiddenTriggerRow) => (
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
          <Button type="link" danger onClick={() => deleteRow(message, row.content, reload)}>
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
            await saveRow(message, content, oldContent, reload);
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
