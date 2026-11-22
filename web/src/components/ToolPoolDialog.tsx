/** 工具池浮层（web-workbench-interactions）— skills / MCP 各自弹层。
 *
 * 数据来自 /status（mount 时已拉取，零额外请求）；形制对齐 mem-dialog
 * （mask + 2px 墨线面板 + 硬投影）。chip 点击 → 层内 state 切换。
 */

import { useState } from "react";
import { useApp } from "../store";
import type { RuntimeStatus } from "../lib/types";

interface PoolRow {
  key: string;
  label: string;
  detail: string;
}

function skillRows(status: RuntimeStatus): PoolRow[] {
  return (status.skills || []).map((s) => ({
    key: String(s.skill_id ?? s.name ?? "?"),
    label: String(s.name ?? s.skill_id ?? "?"),
    detail: "",
  }));
}

function mcpRows(status: RuntimeStatus): PoolRow[] {
  return (status.mcp || []).map((m) => {
    const health = String(m.health_state ?? "?");
    const tools = m.tool_count != null ? `${m.tool_count} tools` : "";
    const transport = String(m.transport ?? "");
    return {
      key: String(m.name ?? "?"),
      label: String(m.name ?? "?"),
      detail: [transport, tools, `health: ${health}`].filter(Boolean).join(" · "),
    };
  });
}

export function ToolPoolDialog({
  kind,
  onClose,
}: {
  kind: "skills" | "mcp";
  onClose: () => void;
}) {
  const { state } = useApp();
  const status = state.status;
  const rows = status ? (kind === "skills" ? skillRows(status) : mcpRows(status)) : [];
  const title = kind === "skills" ? "Skills 工具池" : "MCP Server 工具池";

  return (
    <div
      className="mem-dialog-mask"
      onClick={onClose}
      data-testid={`tool-pool-${kind}`}
    >
      <div
        className="mem-dialog"
        onClick={(e) => e.stopPropagation()}
        style={{ minWidth: 320 }}
      >
        <div className="dialog-title">{title}（{rows.length}）</div>
        <div className="dialog-body" style={{ maxHeight: "50vh", overflowY: "auto" }}>
          {rows.length === 0 && <div className="muted">（空）</div>}
          {rows.map((r) => (
            <div
              key={r.key}
              className="pool-row"
              data-testid={`pool-row-${r.key}`}
            >
              <span className="pool-name">{r.label}</span>
              {r.detail && <span className="pool-detail">{r.detail}</span>}
            </div>
          ))}
        </div>
        <div className="dialog-actions">
          <button className="px-btn-secondary" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

/** composer 上沿的工具池 chip 行：各自弹层。空集合不显示对应 chip。 */
export function ToolPoolChips() {
  const { state } = useApp();
  const [open, setOpen] = useState<"skills" | "mcp" | null>(null);
  const skills = state.status?.skills ?? [];
  const mcp = state.status?.mcp ?? [];

  return (
    <>
      <div className="pool-chip-row" data-testid="pool-chip-row">
        {skills.length > 0 && (
          <button
            className="pool-chip"
            onClick={() => setOpen("skills")}
            data-testid="pool-chip-skills"
          >
            {skills.length} skills ▾
          </button>
        )}
        {mcp.length > 0 && (
          <button
            className="pool-chip"
            onClick={() => setOpen("mcp")}
            data-testid="pool-chip-mcp"
          >
            {mcp.length} MCP ▾
          </button>
        )}
      </div>
      {open && <ToolPoolDialog kind={open} onClose={() => setOpen(null)} />}
    </>
  );
}
