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
  const { state } = useApp();
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
        {state.thinkingVisible && <ThinkingRow text={turn.thinking} />}
        <Markdown text={turn.content} />
        {turn.streaming && <span className="cursor" />}
        {(turn.toolCalls ?? []).map((tool, i) => (
          <ToolCard key={i} tool={tool} />
        ))}
        {turn.budget && (
          <div className="budget">
            <IconCoinStack size={11} color="var(--c-user)" /> 上下文预算 {Math.round(turn.budget.fraction * 100)}%（窗口 {turn.budget.window}）
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
  const [notice, setNotice] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [suggestIndex, setSuggestIndex] = useState(0);
  const [suggestClosed, setSuggestClosed] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);

  // 自动滚到最新
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [state.turns, state.history]);

  // /skill 命令本地处理（web-skill-override）：不发模型，与面板共享 override 状态
  const handleSkillCommand = (text: string) => {
    const arg = text.replace(/^\/skill/, "").trim();
    if (arg === "") {
      setNotice("用法：/skill list | /skill <name> | /skill off");
      return;
    }
    if (arg === "list") {
      actions.refreshSkills();
      setListOpen(true);
      setNotice(null);
      return;
    }
    if (arg === "off") {
      actions.setSkillOverride([]);
      setNotice("已清除 skill override");
      return;
    }
    if (arg === "search" || arg === "install" || arg === "evolve" || arg === "capture"
      || arg === "enable" || arg === "disable" || arg === "history") {
      setNotice(`web 暂不支持 /skill ${arg.split(" ")[0]}；可用：list / <name> / off（启停请用 Skills 面板）`);
      return;
    }
    // <name>：设置会话级 override（未知名由 Selector 静默跳过，语义与 CLI 一致）
    const name = arg.split(/\s+/)[0];
    actions.setSkillOverride([name]);
    setNotice(`skill override 已设置：${name}（/skill off 清除）`);
  };

  const send = () => {
    const text = draft.trim();
    if (!text || state.streaming || !state.currentSessionId) return;
    // /skill 前缀先于一切发送路径（含 running 时的排队语义）本地消化
    if (text.startsWith("/skill")) {
      setDraft("");
      handleSkillCommand(text);
      return;
    }
    setDraft("");
    setNotice(null);
    setListOpen(false);
    actions.send(mode, text);
  };

  // ---- 斜杠补全（command-completion）：光标锚定弹层 + 键盘 ----
  const skillNames = state.skills.map((s) => s.name);
  const commands = [{ text: "/skill", meta: "skill 管理" }];

  const caret = taRef.current?.selectionStart ?? draft.length;
  const beforeCaret = draft.slice(0, caret);
  const trimmed = beforeCaret.trimStart();
  const items: { text: string; meta: string }[] = (() => {
    if (!trimmed.startsWith("/")) return [];
    // 命令位：/xxx（无空白）
    if (!/\s/.test(trimmed)) {
      return commands.filter((c) => c.text.startsWith(trimmed.toLowerCase()));
    }
    // /skill 参数位：子命令优先，无命中补激活 skill 名（数据同 Configs 面板）
    const m = trimmed.match(/^\/skill\s+(\S*)$/);
    if (!m) return [];
    const arg = m[1].toLowerCase();
    const subs = ["list", "off"].filter((s) => s.startsWith(arg) && s !== arg);
    const names = skillNames.filter(
      (n) => n.toLowerCase().startsWith(arg) && n.toLowerCase() !== arg,
    );
    return [
      ...subs.map((s) => ({ text: s, meta: "subcommand" })),
      ...names.map((n) => ({ text: n, meta: "skill" })),
    ];
  })();
  const popupOpen = items.length > 0 && !suggestClosed;

  // 草稿变化 → 重置选中与关闭态
  useEffect(() => {
    setSuggestIndex(0);
    setSuggestClosed(false);
  }, [draft]);

  /** 镜像测量光标 x（弹层锚定在斜杠处）。失败回退 0。 */
  const measureCaretLeft = (): number => {
    try {
      const el = taRef.current;
      const mirror = mirrorRef.current;
      if (!el || !mirror) return 0;
      const cs = window.getComputedStyle(el);
      mirror.style.font = cs.font;
      mirror.style.padding = cs.padding;
      mirror.style.boxSizing = "border-box";
      mirror.style.width = `${el.clientWidth}px`;
      mirror.textContent = draft.slice(0, el.selectionStart ?? draft.length);
      const marker = document.createElement("span");
      marker.textContent = "​";
      mirror.appendChild(marker);
      return Math.max(0, marker.offsetLeft - el.scrollLeft);
    } catch {
      return 0;
    }
  };

  const acceptSuggestion = (value: string) => {
    const el = taRef.current;
    const pos = el?.selectionStart ?? draft.length;
    const b = draft.slice(0, pos);
    const wordStart = Math.max(b.lastIndexOf(" "), b.lastIndexOf("\t")) + 1;
    const insert = value.endsWith(" ") ? value : value + " ";
    const next = draft.slice(0, wordStart) + insert + draft.slice(pos);
    setDraft(next);
    requestAnimationFrame(() => {
      const p2 = wordStart + insert.length;
      el?.focus();
      el?.setSelectionRange(p2, p2);
    });
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
      {notice && (
        <div className="notice" data-testid="skill-cmd-notice">
          {notice}
        </div>
      )}
      {listOpen && (
        <div className="skill-cmd-list" data-testid="skill-cmd-list">
          {state.skills.length === 0
            ? "（无激活 skill）"
            : state.skills.map((s) => (
                <div key={s.skill_id} className="skill-cmd-item">
                  <span className={s.enabled ? "" : "off"}>{s.name}</span>
                  <small>{s.enabled ? "已启用" : "已禁用"}</small>
                </div>
              ))}
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
        <div className="composer-field">
          {popupOpen && (
            <div
              className="slash-popup"
              data-testid="slash-popup"
              style={{ left: measureCaretLeft() }}
            >
              {items.map((s, i) => (
                <div
                  key={`${s.meta}-${s.text}`}
                  className={`slash-item${i === suggestIndex ? " on" : ""}`}
                  data-testid={`slash-item-${s.text}`}
                  onMouseDown={(e) => {
                    e.preventDefault(); // 保持输入框焦点
                    acceptSuggestion(s.text);
                  }}
                >
                  <span>{s.text}</span>
                  {s.meta && <small>{s.meta}</small>}
                </div>
              ))}
            </div>
          )}
          <div className="slash-mirror" ref={mirrorRef} aria-hidden="true" />
          <textarea
            ref={taRef}
            placeholder={state.currentSessionId ? "输入问题，Enter 发送（Shift+Enter 换行）" : "先选择会话"}
            value={draft}
            disabled={!state.currentSessionId || state.streaming}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // command-completion：弹层打开时 ↑↓/Tab/Esc 优先
              if (popupOpen) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setSuggestIndex((i) => Math.min(items.length - 1, i + 1));
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setSuggestIndex((i) => Math.max(0, i - 1));
                  return;
                }
                if (e.key === "Tab") {
                  e.preventDefault();
                  acceptSuggestion(items[Math.min(suggestIndex, items.length - 1)].text);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setSuggestClosed(true);
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            data-testid="composer"
          />
        </div>
        <button className="px-btn send" onClick={send} disabled={state.streaming || !draft.trim()} data-testid="send">
          {state.streaming ? "流式…" : "发送"}
        </button>
      </div>
    </>
  );
}
