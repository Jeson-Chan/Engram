import { useEffect, useState } from "react";
import { AppProvider, useApp } from "./store";
import { SessionRail } from "./components/SessionRail";
import { Conversation } from "./components/Conversation";
import { RunInspector } from "./components/RunInspector";
import { MemoryExplorer } from "./components/MemoryExplorer";
import "./styles.css";

/** 响应式三栏壳：窄屏（<900px）收起 Inspector 与会话栏（可开抽屉）。 */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function Shell() {
  const { state, actions } = useApp();
  const narrow = useNarrow();
  const [drawer, setDrawer] = useState<"sessions" | "run" | "memory" | null>(null);

  useEffect(() => {
    actions.refreshSessions();
    actions.refreshStatus();
  }, [actions]);

  useEffect(() => {
    // 刷新后恢复（任务 5.7 一部分：URL 状态即选中会话）
    const sid = new URLSearchParams(window.location.search).get("s");
    if (sid && state.sessions.some((s) => s.session_id === sid)) {
      actions.selectSession(sid);
    }
  }, [state.sessions]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const sid = state.currentSessionId;
    const url = new URL(window.location.href);
    if (sid) url.searchParams.set("s", sid);
    else url.searchParams.delete("s");
    window.history.replaceState(null, "", url);
  }, [state.currentSessionId]);

  const inspector = (
    <div className="inspector" data-testid="inspector">
      <div className="tabbar">
        <button
          className={state.inspectorTab === "run" ? "on" : ""}
          onClick={() => actions.setInspectorTab("run")}
        >
          Run
        </button>
        <button
          className={state.inspectorTab === "memory" ? "on" : ""}
          onClick={() => actions.setInspectorTab("memory")}
        >
          Memory
        </button>
      </div>
      {state.inspectorTab === "run" ? <RunInspector /> : <MemoryExplorer />}
    </div>
  );

  if (narrow) {
    return (
      <div className="shell narrow">
        <div className="chat">
          <div className="statusbar">
            <button className="drawer-toggle" onClick={() => setDrawer(drawer === "sessions" ? null : "sessions")}>
              会话
            </button>
            <button
              className="drawer-toggle"
              onClick={() => {
                setDrawer(drawer === "run" ? null : "run");
                actions.setInspectorTab("run");
              }}
            >
              Run
            </button>
            <button
              className="drawer-toggle"
              onClick={() => {
                setDrawer(drawer === "memory" ? null : "memory");
                actions.setInspectorTab("memory");
              }}
            >
              Memory
            </button>
            <span className="dot-label">
              {state.status ? state.status.model : state.statusError ? "网关不可用" : "…"}
            </span>
          </div>
          {drawer === "sessions" && <SessionRail />}
          {drawer === "run" && inspector}
          {drawer === "memory" && inspector}
          <Conversation />
        </div>
      </div>
    );
  }

  return (
    <div className="shell" data-narrow={narrow ? "1" : "0"}>
      <SessionRail />
      <div className="chat">
        <div className="statusbar" data-testid="statusbar">
          <span className="dot" />
          <span className="dot-label" data-testid="model-name">
            {state.status ? state.status.model : state.statusError ? "网关不可用" : "…"}
          </span>
          {state.status?.mode && <span className="badge">{state.status.mode}</span>}
          {state.status?.skills && state.status.skills.length > 0 && (
            <span className="badge">{state.status.skills.length} skills</span>
          )}
          {state.status?.mcp && state.status.mcp.length > 0 && (
            <span className="badge">{state.status.mcp.length} MCP</span>
          )}
        </div>
        <Conversation />
      </div>
      {inspector}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
