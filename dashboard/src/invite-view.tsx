// 页面层：邀请树。上面按 QQ 号跨群查树，下面放全部邀请记录表。
// 树只读；节点上限由后端控制，截断时页面提示。

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Empty,
  Input,
  Pagination,
  Space,
  Table,
  Tag,
  Tree,
} from "antd";
import type { TableProps } from "antd";
import { apiPost, getBridge, readError } from "./bridge";
import type {
  GroupNameItem,
  GroupNameListResponse,
  InviteEdgeListResponse,
  InviteEdgeRow,
  InviteGroupTree,
  InviteTreeNode,
  InviteTreeResponse,
} from "./types";

// 列定义数组；TableProps 里的类型带 undefined，拼不起来，这里去掉
type InviteColumns = NonNullable<TableProps<InviteEdgeRow>["columns"]>;

// antd Tree 要 key 和 title，children 再递归；业务字段在拼 title 时已经用掉。
interface InviteTreeRow {
  key: string;
  title: ReactNode;
  children: InviteTreeRow[];
}

function itemsToNameMap(items: GroupNameItem[]): Record<string, string> {
  // 映射表对照群号。没保存过的群显示空。
  const map: Record<string, string> = {};
  for (const item of items || []) {
    const groupId = String(item.group_id || "").trim();
    // 空群号对不上邀请记录
    if (!groupId) {
      continue;
    }
    map[groupId] = String(item.group_name || "").trim();
  }
  return map;
}

function subTypeLabel(value: string): string {
  // 两种入群方式给中文，其它原样显示
  if (value === "invite") {
    return "邀请入群";
  }
  if (value === "approve") {
    return "审批入群";
  }
  return value;
}

function nodeTitle(node: InviteTreeNode): ReactNode {
  // 本人打标签，入群方式和时间跟在号码后面
  return (
    <span>
      {node.user_id}
      {node.is_target ? (
        <Tag color="blue" style={{ marginLeft: 6 }}>
          本人
        </Tag>
      ) : null}
      {node.inviter_id ? (
        <span className="invite-meta">
          {subTypeLabel(node.sub_type)} {node.created_at}
        </span>
      ) : null}
    </span>
  );
}

function toTreeData(nodes: InviteTreeNode[]): InviteTreeRow[] {
  // 递归换成 antd 的 treeData；后端已经把节点数卡在上限内
  return (nodes || []).map((node) => ({
    key: node.user_id,
    title: nodeTitle(node),
    children: toTreeData(node.children),
  }));
}

export function InviteView() {
  // message 从 useApp 取；静态 message 不跟随宿主明暗主题
  const { message } = AntdApp.useApp();
  const [qq, setQq] = useState("");
  const [searchedQq, setSearchedQq] = useState("");
  const [trees, setTrees] = useState<InviteGroupTree[]>([]);
  const [searching, setSearching] = useState(false);
  // 每次搜索自增，用来重建树，避免第二次搜索后节点仍是折叠的
  const [searchSeq, setSearchSeq] = useState(0);

  const [names, setNames] = useState<Record<string, string>>({});
  const [filterGroup, setFilterGroup] = useState("");
  const [filterQq, setFilterQq] = useState("");
  const [appliedGroup, setAppliedGroup] = useState("");
  const [appliedQq, setAppliedQq] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<InviteEdgeRow[]>([]);
  const [loading, setLoading] = useState(false);

  const loadList = useCallback(
    async (nextPage: number, nextSize: number, groupId: string, userId: string) => {
      setLoading(true);
      try {
        const result = await apiPost<InviteEdgeListResponse>("invite/list", {
          group_id: groupId,
          user_id: userId,
          page: nextPage,
          page_size: nextSize,
        });
        setRows(result.items || []);
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
      // 映射失败也把邀请记录拉出来
      if (!cancelled) {
        await loadList(1, 20, "", "");
      }
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, [message, loadList]);

  async function searchTree() {
    const text = qq.trim();
    // 空号码不发请求
    if (!text) {
      message.error("先填 QQ 号。");
      return;
    }
    setSearching(true);
    try {
      const result = await apiPost<InviteTreeResponse>("invite/tree", {
        user_id: text,
      });
      setTrees(result.groups || []);
      setSearchedQq(result.user_id || text);
      setSearchSeq((value) => value + 1);
    } catch (error) {
      message.error(readError(error));
    }
    setSearching(false);
  }

  const columns: InviteColumns = [
    { title: "群号", dataIndex: "group_id", key: "group_id", width: 140 },
    {
      title: "群名",
      key: "group_name",
      render: (_value: unknown, row: InviteEdgeRow) => names[row.group_id] || "",
    },
    { title: "被邀请人", dataIndex: "user_id", key: "user_id", width: 150 },
    { title: "邀请人", dataIndex: "inviter_id", key: "inviter_id", width: 150 },
    {
      title: "方式",
      dataIndex: "sub_type",
      key: "sub_type",
      width: 100,
      render: (value: string) => subTypeLabel(value),
    },
    { title: "记录时间", dataIndex: "created_at", key: "created_at" },
  ];

  return (
    <>
      <Card title="按 QQ 号查邀请树" style={{ marginBottom: 16 }}>
        <p className="hint">
          输入 QQ 号后回车或点查询。会跨群找他出现过的每一棵树，从最顶层邀请人往下展开；树太大时只显示前一部分。
        </p>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            style={{ width: 240 }}
            placeholder="输入 QQ 号后回车"
            value={qq}
            onChange={(event) => setQq(event.target.value)}
            onPressEnter={searchTree}
          />
          <Button type="primary" loading={searching} onClick={searchTree}>
            查询
          </Button>
        </Space>
        {searchedQq && trees.length === 0 ? (
          <Empty description={`没有找到 ${searchedQq} 的邀请记录`} />
        ) : null}
        {trees.map((group) => (
          <Card
            key={`${searchSeq}/${group.group_id}`}
            size="small"
            style={{ marginBottom: 12 }}
            title={`群 ${group.group_id}${names[group.group_id] ? ` ${names[group.group_id]}` : ""}`}
          >
            {group.truncated ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message="树太大，只显示了一部分节点。"
              />
            ) : null}
            <Tree treeData={toTreeData(group.nodes)} defaultExpandAll selectable={false} />
          </Card>
        ))}
      </Card>
      <Card title="全部邀请记录">
        <p className="hint">
          按群号或 QQ 号过滤，QQ 号匹配被邀请人和邀请人两侧。退群不删记录，再进会覆盖成最新邀请人。
        </p>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            style={{ width: 160 }}
            placeholder="按群号过滤"
            value={filterGroup}
            onChange={(event) => setFilterGroup(event.target.value)}
          />
          <Input
            style={{ width: 180 }}
            placeholder="按 QQ 号过滤"
            value={filterQq}
            onChange={(event) => setFilterQq(event.target.value)}
          />
          <Button
            onClick={() => {
              setAppliedGroup(filterGroup.trim());
              setAppliedQq(filterQq.trim());
              loadList(1, pageSize, filterGroup.trim(), filterQq.trim());
            }}
          >
            筛选
          </Button>
        </Space>
        <Table
          rowKey={(row) => `${row.group_id}/${row.user_id}`}
          columns={columns}
          dataSource={rows}
          loading={loading}
          pagination={false}
          size="small"
        />
        <div className="pager">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger
            onChange={(nextPage, nextSize) =>
              loadList(nextPage, nextSize, appliedGroup, appliedQq)
            }
          />
        </div>
      </Card>
    </>
  );
}
