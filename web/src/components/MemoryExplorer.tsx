import { useEffect, useState } from "react";
import { useApp } from "../store";
import type { MemoryTraceView } from "../lib/types";

export function MemoryExplorer() {
  const { state, actions } = useApp();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [layer, setLayer] = useState("");
  const [minStrength, setMinStrength] = useState(0);

  useEffect(() => {
    actions.refreshMemory();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = () => {
    actions.refreshMemory({
      q: q || undefined,
      type: type || undefined,
      layer: layer || undefined,
      minStrength: minStrength || undefined,
    });
  };

  const stats = state.memoryStats;
  return (
    <div data-testid="memory-explorer">
      <div className="panel-title">记忆浏览</div>
      {stats && (
        <div className="mem-stats" data-testid="memory-stats">
          <span className="stat">全部 <b>{stats.total ?? 0}</b></span>
          <span className="stat">热层 <b>{stats.hot ?? 0}</b></span>
          <span className="stat">冷层 <b>{stats.cold ?? 0}</b></span>
          <span className="stat">已遗忘 <b>{stats.forgotten ?? 0}</b></span>
          <span className="stat">巩固 <b>{stats.consolidation ?? 0}</b></span>
        </div>
      )}
      <div className="mem-controls">
        <input
          placeholder="搜索记忆内容…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          data-testid="memory-search"
        />
        <div style={{ display: "flex", gap: 6 }}>
          <select value={type} onChange={(e) => setType(e.target.value)} data-testid="memory-type">
            <option value="">全部类型</option>
            <option value="episodic">episodic</option>
            <option value="semantic">semantic</option>
            <option value="procedural">procedural</option>
          </select>
          <select value={layer} onChange={(e) => setLayer(e.target.value)} data-testid="memory-layer">
            <option value="">全部层</option>
            <option value="hot">热层</option>
            <option value="cold">冷层</option>
          </select>
          <select
            value={minStrength}
            onChange={(e) => setMinStrength(Number(e.target.value))}
            data-testid="memory-strength"
          >
            <option value={0}>任意强度</option>
            <option value={0.3}>强度 ≥ 0.3</option>
            <option value={0.6}>强度 ≥ 0.6</option>
          </select>
          <button className="mode-btn" onClick={apply} data-testid="memory-apply">
            筛选
          </button>
        </div>
      </div>
      {state.memoryTraces.length === 0 && (
        <div className="empty">没有匹配的记忆<br /><small>对话后自动沉淀；也可运行 seed 演示数据</small></div>
      )}
      {state.memoryTraces.map((m: MemoryTraceView) => (
        <div className="mem-item" key={m.id} data-testid="memory-item">
          <div className="row1">
            <span className="tag">{m.type}</span>
            {m.layer && <span className={`tag ${m.layer}`}>{m.layer === "hot" ? "热" : "冷"}</span>}
            {m.forgotten && <span className="tag forgotten">已遗忘</span>}
            <span className="strength-bar" title={`strength ${m.strength}`}>
              <div style={{ width: `${Math.round(m.strength * 100)}%` }} />
            </span>
          </div>
          <div className="content">{m.content}</div>
          <div className="meta">
            {m.source || ""} · 访问 {m.access_count} 次
            {m.created_at ? ` · ${m.created_at.slice(0, 16).replace("T", " ")}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
