import { useEffect, useRef, useState } from "react";
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

  // 刷新恢复（任务 5.7）：mount 时刻缓存 URL 里的 ?s=——URL-clear effect
  // 在 currentSessionId 仍为 null 的首帧就会删参数，晚读就丢了
  const initialSid = useRef(
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("s")
      : null,
  );

  useEffect(() => {
    actions.refreshSessions();
    actions.refreshStatus();
  }, [actions]);

  useEffect(() => {
    const sid = initialSid.current;
    if (sid && state.sessions.some((s) => s.session_id === sid)) {
      actions.selectSession(sid);
      initialSid.current = null; // 恢复一次即失效（后续切换由选中状态驱动）
    }
  }, [state.sessions]); // eslint-disable-line react-hooks/exhaustive-deps

  // URL 同步：跳过首帧（mount 时 currentSessionId 尚为 null，会把 ?s= 清掉）
  const firstUrlSync = useRef(true);
  useEffect(() => {
    if (firstUrlSync.current) {
      firstUrlSync.current = false;
      // 首帧仍要同步（选中会话后正常写 URL），只是不清参数
      if (state.currentSessionId) {
        const url = new URL(window.location.href);
        url.searchParams.set("s", state.currentSessionId);
        window.history.replaceState(null, "", url);
      }
      return;
    }
    const sid = state.currentSessionId;
    const url = new URL(window.location.href);
    if (sid) url.searchParams.set("s", sid);
    else url.searchParams.delete("s");
    window.history.replaceState(null, "", url);
  }, [state.currentSessionId]);

  const inspector = (drawerMode = false) => (
    <div
      className={drawerMode ? "inspector drawer-inspector" : "inspector"}
      data-testid="inspector"
    >
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
          {drawer === "sessions" && <SessionRail drawer />}
          {drawer === "run" && inspector(true)}
          {drawer === "memory" && inspector(true)}
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
      {inspector()}
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
