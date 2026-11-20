import { useApp } from "../store";
import type { SessionRecord } from "../lib/api";
import { IconSession, IconMemory } from "./pixel-icons";

/** GitHub 仓库主页同款 logo(web-pixel-flavor-a 收口轮)。
 *  直接内嵌 docs/assets/engram-logo.gif(1200x480,自带紫→青渐变 +
 *  glint 扫光)——与 README/GitHub 展示完全一致,零失真。
 *  宽度撑满 rail 内容区;image-rendering 保持像素锐利。 */
import logoGif from "../assets/engram-logo.gif";

export function PixelWordmark() {
  return (
    <div className="wordmark" data-testid="wordmark">
      <img
        src={logoGif}
        alt="ENGRAM"
        style={{ width: "100%", height: "auto", imageRendering: "pixelated", display: "block" }}
      />
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
          <IconSession size={13} /> 会话
        </button>
        <button
          className={state.mainView === "memory" ? "on" : ""}
          onClick={() => actions.setMainView("memory")}
          data-testid="nav-memory"
          data-nav="memory"
        >
          <IconMemory size={13} /> 记忆
        </button>
      </div>
      <div className="px-panel-bar">会话</div>
      <button className="px-btn" onClick={() => actions.createSession()}>
        <IconSession size={11} /> 新建会话
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
