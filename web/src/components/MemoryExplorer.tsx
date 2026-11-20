/**
 * 记忆管理页（memory-management-ui）— 全宽主页面。
 *
 * 布局：分区树（user → thread，条数来自列表聚合）+ 全宽记忆列表。
 * 交互：逐条勾选/全选、单条删除（一次点击）、thread/user 清除
 * （确认框先 preview 展示将删条数）、来源跳转回会话、503 空态。
 */

import { useMemo, useState } from "react";
import { useApp } from "../store";
import type { MemoryTraceView } from "../lib/types";
import { IconMemory, IconHot, IconCold, IconDelete, IconClear } from "./pixel-icons";

/** 从 source 推导归属 thread（与后端 _thread_of / store _partition_of 同语义）。 */
export function threadOf(trace: MemoryTraceView): string {
  const source = trace.source || "";
  if (source.startsWith("worker:")) return source.split(":")[1] || "default";
  return "default";
}

interface ConfirmState {
  grain: "thread" | "user";
  userId: string;
  threadId: string | null;
  /** null = 预览加载中；-1 = 预览失败 */
  count: number | null;
}

/** 斜纹强度条:45deg 条纹填充(宽度 = strength 比例),青色 currentColor。 */
export function PixelStrength({ strength }: { strength: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, strength)) * 100);
  return (
    <span
      className="stripe-bar"
      style={{ width: 64, color: "var(--c-agent)", display: "inline-block" }}
      data-testid={`strength-${strength}`}
      title={`strength ${strength}`}
    >
      <span style={{ display: "block", width: `${pct}%` }} />
    </span>
  );
}

export function MemoryExplorer() {
  const { state, actions } = useApp();
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [busy, setBusy] = useState(false);

  const { memFilters, memPartition, memSelected } = state;
  const traces = state.memoryTraces;

  // ---- 分区树聚合（user → thread，来自当前 user 全量列表） ----
  const tree = useMemo(() => {
    const threads = new Map<string, number>();
    for (const t of traces) {
      const th = threadOf(t);
      threads.set(th, (threads.get(th) || 0) + 1);
    }
    return [...threads.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [traces]);

  // ---- 列表：分区过滤 + 显示筛选（全部前端聚合） ----
  const visible = useMemo(() => {
    const q = memFilters.q.trim().toLowerCase();
    return traces.filter((t) => {
      if (memPartition && threadOf(t) !== memPartition.threadId) return false;
      if (q && !(t.content || "").toLowerCase().includes(q)) return false;
      if (memFilters.type && t.type !== memFilters.type) return false;
      if (memFilters.layer && (t.layer || "") !== memFilters.layer) return false;
      if (memFilters.minStrength > 0 && t.strength < memFilters.minStrength) return false;
      return true;
    });
  }, [traces, memPartition, memFilters]);

  const visibleIds = useMemo(() => visible.map((t) => t.id), [visible]);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => memSelected.includes(id));

  if (state.memoryUnavailable) {
    return (
      <div className="memory-page" data-testid="memory-explorer">
        <div className="memory-page-head">
          <div className="panel-title">记忆管理</div>
        </div>
        <div className="empty" data-testid="memory-unavailable">
          记忆未配置
          <br />
          <small>设置 ENGRAM_MEMORY_USE 与 Redis/PG 后可用</small>
        </div>
      </div>
    );
  }

  const openConfirm = async (grain: "thread" | "user", userId: string, threadId: string | null) => {
    setConfirm({ grain, userId, threadId, count: null });
    const count = await actions.previewMemoryPartition(userId, threadId ?? undefined);
    setConfirm((cur) => (cur && cur.userId === userId && cur.threadId === threadId
      ? { ...cur, count } : cur));
  };

  const doClear = async () => {
    if (!confirm || confirm.count === null || confirm.count < 0) return;
    setBusy(true);
    try {
      await actions.clearMemoryPartition(confirm.userId, confirm.threadId ?? undefined);
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  const doDeleteSelected = async () => {
    setBusy(true);
    try {
      for (const id of memSelected) {
        await actions.deleteMemoryTrace(id);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="memory-page" data-testid="memory-explorer">
      <div className="memory-page-head">
        <div className="panel-title">记忆管理</div>
        <span className="badge">{state.user_id}</span>
        <span className="mem-stats" data-testid="memory-stats" style={{ display: "inline-flex", gap: 8 }}>
        <span className="stat"><IconMemory size={10} /> 全部 <b>{state.memoryStats?.total ?? 0}</b></span>
        <span className="stat"><IconHot size={10} color="var(--c-exec)" /> 热层 <b>{state.memoryStats?.hot ?? 0}</b></span>
        <span className="stat"><IconCold size={10} /> 冷层 <b>{state.memoryStats?.cold ?? 0}</b></span>
        </span>
        <button className="ghost-btn" onClick={() => actions.setMainView("chat")}>
          返回会话
        </button>
      </div>

      <div className="memory-body">
        <div className="mem-tree" data-testid="memory-tree">
          <div className="tree-node">
            <span
              className={`tree-label${memPartition === null ? " on" : ""}`}
              onClick={() => actions.setMemPartition(null)}
              data-testid="tree-user"
            >
              全部记忆 <small>({traces.length})</small>
            </span>
            <button
              className="tree-clear"
              title="清除该用户的全部记忆"
              disabled={traces.length === 0}
              onClick={() => openConfirm("user", state.user_id, null)}
              data-testid="tree-user-clear"
            >
              <IconClear size={9} /> 清除
            </button>
          </div>
          {tree.map(([thread, count]) => (
            <div className="tree-node" key={thread}>
              <span
                className={`tree-label${memPartition?.threadId === thread ? " on" : ""}`}
                onClick={() => actions.setMemPartition({ userId: state.user_id, threadId: thread })}
                data-testid={`tree-thread-${thread}`}
              >
                {thread} <small>({count})</small>
              </span>
              <button
                className="tree-clear"
                title="清除该会话沉淀的记忆"
                onClick={() => openConfirm("thread", state.user_id, thread)}
                data-testid={`tree-thread-clear-${thread}`}
              >
                清除
              </button>
            </div>
          ))}
        </div>

        <div className="mem-list-wrap">
          <div className="mem-controls">
            <input
              placeholder="搜索记忆内容…"
              value={memFilters.q}
              onChange={(e) => actions.setMemFilters({ q: e.target.value })}
              data-testid="memory-search"
            />
            <select
              value={memFilters.type}
              onChange={(e) => actions.setMemFilters({ type: e.target.value })}
              data-testid="memory-type"
            >
              <option value="">全部类型</option>
              <option value="episodic">episodic</option>
              <option value="semantic">semantic</option>
              <option value="procedural">procedural</option>
            </select>
            <select
              value={memFilters.layer}
              onChange={(e) => actions.setMemFilters({ layer: e.target.value })}
              data-testid="memory-layer"
            >
              <option value="">全部层</option>
              <option value="hot">热层</option>
              <option value="cold">冷层</option>
            </select>
            <select
              value={String(memFilters.minStrength)}
              onChange={(e) => actions.setMemFilters({ minStrength: Number(e.target.value) })}
              data-testid="memory-strength"
            >
              <option value="0">任意强度</option>
              <option value="0.3">强度 ≥ 0.3</option>
              <option value="0.6">强度 ≥ 0.6</option>
            </select>
            <label className="select-all">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() =>
                  actions.setMemSelected(allSelected ? [] : visibleIds)
                }
                data-testid="memory-select-all"
              />
              全选
            </label>
          </div>

          {visible.length === 0 && (
            <div className="empty" data-testid="memory-empty-list">
              没有匹配的记忆<br />
              <small>对话后自动沉淀</small>
            </div>
          )}

          {visible.map((m) => (
            <div className="mem-item" key={m.id} data-testid={`memory-item-${m.id}`}>
              <input
                type="checkbox"
                checked={memSelected.includes(m.id)}
                onChange={() => actions.toggleMemSelected(m.id)}
                data-testid={`memory-check-${m.id}`}
              />
              <div className="mem-item-main">
                <div className="row1">
                  <span className="tag">{m.type}</span>
                  {m.layer && (
                    <span className={`tag ${m.layer}`}>
                      {m.layer === "hot"
                      ? <IconHot size={8} color="var(--c-exec)" />
                      : <IconCold size={8} />} {m.layer === "hot" ? "热" : "冷"}
                    </span>
                  )}
                  {m.forgotten && <span className="tag forgotten">已遗忘</span>}
                  <PixelStrength strength={m.strength} />
                </div>
                <div className="content">{m.content}</div>
                <div className="meta">
                  <span
                    className="source-link"
                    title="跳转到来源会话"
                    onClick={() => actions.openSessionFromMemory(threadOf(m))}
                    data-testid={`memory-source-${m.id}`}
                  >
                    来源 {threadOf(m)}
                  </span>
                  <span>访问 {m.access_count} 次</span>
                  {m.created_at && (
                    <span>{m.created_at.slice(0, 16).replace("T", " ")}</span>
                  )}
                </div>
              </div>
              <button
                className="del"
                disabled={busy}
                onClick={() => actions.deleteMemoryTrace(m.id)}
                data-testid={`memory-delete-${m.id}`}
              >
                <IconDelete size={10} /> 删除
              </button>
            </div>
          ))}
        </div>
      </div>

      {memSelected.length > 0 && (
        <div className="mem-actionbar" data-testid="memory-actionbar">
          <span>已选 {memSelected.length} 条</span>
          <button className="danger-btn" disabled={busy} onClick={doDeleteSelected}>
            <IconDelete size={10} /> 删除选中
          </button>
          <button className="ghost-btn" onClick={() => actions.setMemSelected([])}>
            取消
          </button>
        </div>
      )}

      {confirm && (
        <div className="mem-dialog-mask" data-testid="memory-confirm">
          <div className="mem-dialog">
            <div className="dialog-title">
              {confirm.grain === "user"
                ? `清除用户 ${confirm.userId} 的全部记忆？`
                : `清除会话 ${confirm.threadId} 沉淀的记忆？`}
            </div>
            <div className="dialog-body" data-testid="confirm-count">
              {confirm.count === null
                ? "正在统计将删除的记忆…"
                : confirm.count < 0
                  ? "预览失败，无法确认范围"
                  : confirm.count === 0
                    ? "该分区没有记忆"
                    : `将硬删除 ${confirm.count} 条记忆（不可恢复）`}
              {confirm.grain === "thread" && confirm.count !== null && confirm.count > 0 && (
                <div className="muted">范围：首次诞生于该会话的记忆</div>
              )}
            </div>
            <div className="dialog-actions">
              <button className="ghost-btn" onClick={() => setConfirm(null)}>
                取消
              </button>
              <button
                className="danger-btn"
                disabled={busy || confirm.count === null || confirm.count <= 0}
                onClick={doClear}
                data-testid="confirm-ok"
              >
                <IconClear size={10} /> 确认清除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
