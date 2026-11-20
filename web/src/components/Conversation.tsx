import { useEffect, useRef, useState } from "react";
import { useApp } from "../store";
import { IconCoinStack } from "./pixel-icons";
import { Markdown } from "./Markdown";
import type { ChatTurn, ToolCallState } from "../store";
import type { MessageView } from "../lib/types";

export function ToolCard({ tool }: { tool: ToolCallState }) {
  const [open, setOpen] = useState(false);
  const dur =
    tool.finishedAt != null ? `${((tool.finishedAt - tool.startedAt) / 1000).toFixed(1)}s` : "…";
  return (
    <div className="tool-card" data-testid="tool-card" data-tool-name={tool.name}>
      <div className="head" onClick={() => setOpen(!open)}>
        <span className="name">{tool.name}</span>
        <span className="dur">{dur}</span>
        <span className={`st ${tool.failed ? "fail" : "ok"}`}>
          {tool.failed ? "✗ 失败" : tool.result != null ? "✓" : "…"}
        </span>
      </div>
      {(open || tool.failed) && (
        <details open>
          {tool.args != null && (
            <summary>参数</summary>
          )}
          {tool.args != null && <pre>{JSON.stringify(tool.args, null, 2)}</pre>}
          {tool.result != null && (
            <>
              <summary>结果</summary>
              <pre>{tool.result}</pre>
            </>
          )}
          {tool.result == null && <div>运行中…</div>}
        </details>
      )}
    </div>
  );
}

function RecalledHint({ turn }: { turn: ChatTurn }) {
  if (!turn.memoryRecalled || turn.memoryRecalled.length === 0) return null;
  const n = turn.memoryRecalled.length;
  return (
    <div className="recalled" data-testid="recalled">
      <details>
        <summary>
          本轮召回 <span className="n">{n}</span> 条记忆（点击展开）
        </summary>
        <table>
          <tbody>
            {turn.memoryRecalled.map((m) => (
              <tr key={m.id}>
                <td>{m.id.slice(0, 10)}…</td>
                <td>score {m.score.toFixed(2)}</td>
                <td>strength {m.strength.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function roleClass(role: string): string {
  if (role === "human") return "user";
  if (role === "ai") return "assistant";
  return role;
}

function ThinkingRow({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="recalled thinking" data-testid="thinking-row">
      <details>
        <summary>
          思考过程（{text.length} 字符，点击展开）
        </summary>
        <div style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "var(--muted)" }}>
          {text.slice(0, 2000)}
        </div>
      </details>
    </div>
  );
}

function HistoryMessage({ msg }: { msg: MessageView }) {
  // review medium：tool 消息不渲染成裸气泡（原始输出很长、破坏回放视觉）——
  // 折叠成工具卡摘要行，内容挂在 details 里
  if (msg.role === "tool") {
    return (
      <div className="tool-card" data-testid="history-tool">
        <details>
          <summary>🔧 工具输出（{msg.content.length} 字符，点击展开）</summary>
          <pre>{msg.content.slice(0, 2000)}</pre>
        </details>
      </div>
    );
  }
  return (
    <div className={`msg ${roleClass(msg.role)}`}>
      <div className="role">{msg.role}</div>
      <div className="body">
        <Markdown text={msg.content} />
        {(msg.tool_calls ?? []).map((tc, i) => (
          <div className="tool-card" key={i}>
            <div className="head">
              <span className="name">{tc.name}</span>
              <span className="st ok">✓</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="msg user">
        <div className="role">你</div>
        <div className="body">
          <Markdown text={turn.content} />
        </div>
      </div>
    );
  }
  return (
    <div className="msg assistant">
      <div className="role">
        Engram
        {turn.skillActive && turn.skillActive.length > 0 && (
          <span className="badge">skill: {turn.skillActive.join(", ")}</span>
        )}
      </div>
      <div className="body">
        <RecalledHint turn={turn} />
        <ThinkingRow text={turn.thinking} />
        <Markdown text={turn.content} />
        {turn.streaming && <span className="cursor" />}
        {(turn.toolCalls ?? []).map((tool, i) => (
          <ToolCard key={i} tool={tool} />
        ))}
        {turn.budget && (
          <div className="budget">
            <IconCoinStack size={10} color="var(--c-user)" /> 上下文预算 {Math.round(turn.budget.fraction * 100)}%（窗口 {turn.budget.window}）
            <div className={`bar${turn.budget.fraction >= 0.8 ? " high" : ""}`}>
              <div style={{ width: `${Math.min(100, turn.budget.fraction * 100)}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function Conversation() {
  const { state, actions } = useApp();
  const [mode, setMode] = useState<"chat" | "research">("chat");
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  // 自动滚到最新
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [state.turns, state.history]);

  const send = () => {
    const text = draft.trim();
    if (!text || state.streaming || !state.currentSessionId) return;
    setDraft("");
    actions.send(mode, text);
  };

  return (
    <>
      <div className="msg-list" ref={listRef} data-testid="conversation">
        {!state.currentSessionId && (
          <div className="empty">
            选择左侧会话，或新建一个<br />
            <small>流式对话 / 研究 · 工具轨迹 · 记忆召回 · 断线续传</small>
          </div>
        )}
        {state.history.map((m, i) => (
          <HistoryMessage key={`h-${i}`} msg={m} />
        ))}
        {state.turns.map((turn, i) => (
          <TurnView key={`t-${i}`} turn={turn} />
        ))}
      </div>
      {state.droppedNotice && (
        <div className="notice" data-testid="dropped-notice">
          ⚠ {state.droppedNotice}
        </div>
      )}
      <div className="composer">
        <div className="modes">
          <button
            className={`mode-btn${mode === "chat" ? " on" : ""}`}
            onClick={() => setMode("chat")}
            data-testid="mode-chat"
          >
            对话
          </button>
          <button
            className={`mode-btn${mode === "research" ? " on" : ""}`}
            onClick={() => setMode("research")}
            data-testid="mode-research"
          >
            研究
          </button>
        </div>
        <textarea
          placeholder={state.currentSessionId ? "输入问题，Enter 发送（Shift+Enter 换行）" : "先选择会话"}
          value={draft}
          disabled={!state.currentSessionId || state.streaming}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          data-testid="composer"
        />
        <button className="px-btn send" onClick={send} disabled={state.streaming || !draft.trim()} data-testid="send">
          {state.streaming ? "流式…" : "发送"}
        </button>
      </div>
    </>
  );
}
