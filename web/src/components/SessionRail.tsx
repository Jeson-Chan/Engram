import { useApp } from "../store";
import type { SessionRecord } from "../lib/api";

export function titleOf(record: SessionRecord): string {
  return String(record.metadata?.title || `Session ${record.session_id.slice(0, 8)}`);
}

export function SessionRail({ drawer = false }: { drawer?: boolean }) {
  const { state, actions } = useApp();
  return (
    <div className={`rail${drawer ? " drawer-rail" : ""}`} data-testid="session-rail">
      <div className="nav-tabs" data-testid="rail-nav">
        <button
          className={state.mainView === "chat" ? "on" : ""}
          onClick={() => actions.setMainView("chat")}
          data-testid="nav-sessions"
        >
          会话
        </button>
        <button
          className={state.mainView === "memory" ? "on" : ""}
          onClick={() => actions.setMainView("memory")}
          data-testid="nav-memory"
        >
          记忆
        </button>
      </div>
      <div className="panel-title">会话</div>
      <button className="new-session" onClick={() => actions.createSession()}>
        + 新建会话
      </button>
      {state.sessions.length === 0 && (
        <div className="empty">还没有会话<br />点上方新建一个</div>
      )}
      {state.sessions.map((s) => (
        <div
          key={s.session_id}
          className={`session-item${s.session_id === state.currentSessionId ? " active" : ""}`}
          onClick={() => actions.selectSession(s.session_id)}
          data-testid={`session-${s.session_id.slice(0, 6)}`}
        >
          <div className="title">{titleOf(s)}</div>
          <div className="meta">
            <span>{s.user_id}</span>
            <span>{s.created_at?.slice(0, 16).replace("T", " ")}</span>
            <span
              className="del"
              style={{ marginLeft: "auto", cursor: "pointer" }}
              onClick={(e) => {
                e.stopPropagation();
                actions.deleteSession(s.session_id);
              }}
            >
              删除
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
