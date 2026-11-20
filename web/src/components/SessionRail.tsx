import { useApp } from "../store";
import type { SessionRecord } from "../lib/api";
import { IconSession, IconMemory } from "./pixel-icons";

/** 地牢像素 wordmark:Geist Pixel 双色字母(紫=秘法/青=法力),
 *  火把橙版本号。替代点阵 pre(74 字符宽溢出 rail 的遮挡问题)。 */
export function PixelWordmark() {
  return (
    <div className="wordmark" data-testid="wordmark">
      <div className="glyph">
        <span className="g1">ENG</span>
        <span className="g2">RAM</span>
      </div>
      <div className="wm-sub">
        <span className="pixel-font" style={{ color: "var(--c-exec)" }}>v1.0.0</span>
        <span>记忆工作台</span>
      </div>
    </div>
  );
}

export function titleOf(record: SessionRecord): string {
  return String(record.metadata?.title || `Session ${record.session_id.slice(0, 8)}`);
}

export function SessionRail({ drawer = false }: { drawer?: boolean }) {
  const { state, actions } = useApp();
  return (
    <div className={`rail${drawer ? " drawer-rail" : ""}`} data-testid="session-rail">
      <PixelWordmark />
      <div className="nav-tabs" data-testid="rail-nav">
        <button
          className={state.mainView === "chat" ? "on" : ""}
          onClick={() => actions.setMainView("chat")}
          data-testid="nav-sessions"
          data-nav="sessions"
        >
          <IconSession size={12} /> 会话
        </button>
        <button
          className={state.mainView === "memory" ? "on" : ""}
          onClick={() => actions.setMainView("memory")}
          data-testid="nav-memory"
          data-nav="memory"
        >
          <IconMemory size={12} /> 记忆
        </button>
      </div>
      <div className="panel-title">会话</div>
      <button className="new-session" onClick={() => actions.createSession()}>
        <IconSession size={10} /> 新建会话
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
