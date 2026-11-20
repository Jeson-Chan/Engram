import { useApp } from "../store";
import type { SessionRecord } from "../lib/api";
import { IconSession, IconMemory } from "./pixel-icons";

/** GitHub banner 同款 ▓ 点阵 wordmark(docs/assets/engram-banner.txt),
 *  逐行紫→青渐变着色;5px 字号适配 240px rail(无圆角方块)。 */
const _WM_ROWS = [
  "▓▓▓▓▓▓▓▓▓▓  ▓▓      ▓▓    ▓▓▓▓▓    ▓▓▓▓▓▓▓▓      ▓▓▓▓▓▓    ▓▓      ▓▓",
  "▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓  ▓▓▓▓  ▓▓▓▓",
  "▓▓          ▓▓▓▓    ▓▓  ▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓  ▓▓  ▓▓",
  "▓▓▓▓▓▓▓▓  ▓▓  ▓▓  ▓▓  ▓▓  ▓▓▓▓▓  ▓▓▓▓▓▓▓▓  ▓▓      ▓▓  ▓▓  ▓▓  ▓▓",
  "▓▓          ▓▓    ▓▓▓▓  ▓▓      ▓▓  ▓▓  ▓▓      ▓▓      ▓▓  ▓▓      ▓▓",
  "▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓    ▓▓    ▓▓      ▓▓  ▓▓      ▓▓",
  "▓▓▓▓▓▓▓▓▓  ▓▓      ▓▓    ▓▓▓▓▓    ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓",
];
const _WM_COLORS = ["#a63fc0", "#9a4cc2", "#8d59c3", "#6f74c0", "#5a9cbe", "#4fb8bb", "#45c4b8"];

export function PixelWordmark() {
  const cell = 3;
  const rects: Array<{ x: number; y: number; c: string }> = [];
  _WM_ROWS.forEach((row, ry) => {
    for (let cx = 0; cx < row.length; cx++) {
      if (row[cx] === "▓") {
        rects.push({ x: cx * cell, y: ry * cell, c: _WM_COLORS[ry] });
      }
    }
  });
  return (
    <div className="wordmark" data-testid="wordmark">
      <svg
        width={74 * cell}
        height={7 * cell}
        viewBox={`0 0 ${74 * cell} ${7 * cell}`}
        shapeRendering="crispEdges"
        role="img"
        aria-label="ENGRAM"
      >
        {rects.map((r, i) => (
          <rect key={i} x={r.x} y={r.y} width={cell} height={cell} fill={r.c} />
        ))}
      </svg>
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
