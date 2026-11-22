import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useApp } from "../store";
import type { SessionRecord } from "../lib/api";
import { IconSession, IconMemory, IconEdit } from "./pixel-icons";

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
  // 行内重命名状态：正在编辑的 session_id（null=无）
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // 进入编辑态：input 聚焦 + 全选（autofocus 在条件渲染下不可靠）
  useEffect(() => {
    if (editingId !== null) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editingId]);

  const beginEdit = (s: SessionRecord) => {
    setEditValue(titleOf(s));
    setEditingId(s.session_id);
  };

  const commitEdit = () => {
    if (editingId === null) return;
    const title = editValue.trim();
    const current = titleOf(
      state.sessions.find((s) => s.session_id === editingId)
        ?? { metadata: {}, session_id: editingId } as SessionRecord,
    );
    setEditingId(null);
    // 空值/未变更按取消（不发请求）
    if (!title || title === current) return;
    actions.renameSession(editingId, title);
  };

  const cancelEdit = () => setEditingId(null);

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
      <div className="px-panel-bar" style={{ "--bar-c": "var(--c-user)" } as CSSProperties}>会话</div>
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
          onClick={() => {
            if (editingId === s.session_id) return; // 编辑态点击短路
            actions.selectSession(s.session_id);
          }}
          data-testid={`session-${s.session_id.slice(0, 6)}`}
        >
          {editingId === s.session_id ? (
            <input
              ref={inputRef}
              className="rename-input"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === "Enter") commitEdit();
                if (e.key === "Escape") cancelEdit();
              }}
              onBlur={commitEdit}
              onClick={(e) => e.stopPropagation()}
              data-testid="rename-input"
            />
          ) : (
            <div className="title" data-testid="session-title">{titleOf(s)}</div>
          )}
          {/* 动作键：绝对定位右上角，不参与 meta 的 flex 挤压（防遮挡） */}
          {editingId !== s.session_id && (
            <div className="item-actions">
              <span
                className="del"
                onClick={(e) => {
                  e.stopPropagation();
                  beginEdit(s);
                }}
                title="重命名"
                data-testid={`rename-${s.session_id.slice(0, 6)}`}
              >
                <IconEdit size={10} color="var(--muted)" />
              </span>
              <span
                className="del"
                onClick={(e) => {
                  e.stopPropagation();
                  actions.deleteSession(s.session_id);
                }}
                title="删除"
                data-testid={`delete-${s.session_id.slice(0, 6)}`}
              >
                删除
              </span>
            </div>
          )}
          <div className="meta">
            <span>{s.user_id}</span>
            <span>{s.created_at?.slice(0, 16).replace("T", " ")}</span>
            <span className="sid" data-testid="session-id">{s.session_id.slice(0, 12)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
