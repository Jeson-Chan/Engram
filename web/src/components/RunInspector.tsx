import { useEffect } from "react";
import { useApp } from "../store";
import type { RunRecord, RunEventView } from "../lib/types";

function iconOf(eventType: string): string {
  if (eventType.startsWith("tool.")) return "🔧";
  if (eventType.startsWith("llm")) return "🧠";
  if (eventType.startsWith("memory")) return "🗂";
  if (eventType.startsWith("run")) return "▶";
  if (eventType.startsWith("report")) return "📄";
  return "·";
}

function timelineLabel(event: RunEventView): string {
  if (event.event_type.startsWith("tool.")) {
    const tool = (event.payload as Record<string, unknown>).tool
      ?? (event.payload as Record<string, unknown>).tool_name;
    return `${event.event_type}${tool ? ` · ${tool}` : ""}`;
  }
  return event.event_type;
}

export function RunInspector() {
  const { state, actions } = useApp();
  const currentRun = state.runs.find((r) => r.run_id === state.currentRunId);

  // 打开会话后有 runs 但未选中时默认看最近一次
  useEffect(() => {
    if (!state.currentRunId && state.runs.length > 0) {
      actions.openRun(state.runs[0].run_id);
    }
  }, [state.runs]); // eslint-disable-line react-hooks/exhaustive-deps

  const toolStartEvents = state.runEvents.filter((e) => e.event_type.startsWith("tool."));

  return (
    <div data-testid="run-inspector">
      <div className="panel-title">运行历史</div>
      {state.runs.length === 0 && (
        <div className="empty">本会话还没有运行<br />发一条消息或研究一次</div>
      )}
      <ul className="runs-list">
        {state.runs.map((r: RunRecord) => (
          <li
            key={r.run_id}
            className={`run-item${r.run_id === state.currentRunId ? " on" : ""}`}
            onClick={() => actions.openRun(r.run_id)}
          >
            <span className={`st ${r.status}`}>{r.status}</span>
            {r.run_id.slice(0, 16)}
            <div className="meta" style={{ color: "var(--muted)", fontSize: 11 }}>
              {r.created_at?.slice(5, 16).replace("T", " ")}
              {r.total_tokens != null ? ` · ${r.total_tokens} tok` : ""}
            </div>
          </li>
        ))}
      </ul>

      {currentRun?.report_path && (
        <a
          className="report-link"
          href={`/runs/${currentRun.run_id}/report`}
          target="_blank"
          rel="noreferrer"
          data-testid="report-link"
        >
          预览 / 下载报告（Markdown）
        </a>
      )}

      <div className="panel-title">
        事件时间线 {state.runEvents.length > 0 ? `(${state.runEvents.length})` : ""}
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", padding: "0 12px 6px" }}>
        时间线中的工具节点可与对话区工具卡片互相定位（同一 run 的事实）。
      </div>
      {state.runEvents.map((e) => (
        <div
          key={e.event_id}
          className={`timeline-item ${e.event_type.startsWith("tool.") ? "tool" : ""} ${
            e.event_type === "run.finished" ? "run-done" : ""
          } ${e.event_type === "run.failed" ? "run-failed" : ""}`}
          data-testid="timeline-item"
          data-event-type={e.event_type}
        >
          <div>
            {iconOf(e.event_type)} {timelineLabel(e)}
          </div>
          <div className="t">{e.created_at?.slice(11, 19) || ""}</div>
        </div>
      ))}
      {state.runEvents.length === 0 && state.currentRunId && (
        <div className="empty">该 run 无持久事件日志</div>
      )}
      {toolStartEvents.length > 0 && (
        <div style={{ fontSize: 11, color: "var(--muted)", padding: "6px 12px" }}>
          工具调用 {toolStartEvents.length} 次
        </div>
      )}
    </div>
  );
}
