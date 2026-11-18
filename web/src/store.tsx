/** 应用状态 — React context + useReducer（零外部状态库依赖）。 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { EngramAPI, type SessionRecord } from "./lib/api";
import { parseEventData, streamSSE } from "./lib/sse";
import type {
  MemoryTraceView,
  MessageView,
  RunEventView,
  RunRecord,
  RuntimeStatus,
  StreamEvent,
} from "./lib/types";

export interface ToolCallState {
  name: string;
  args: Record<string, unknown> | null;
  result: string | null;
  startedAt: number;
  finishedAt: number | null;
  failed: boolean;
  /** tool-call id（tool_start/tool_end 都带 msg_id——按 id 配对，review medium） */
  msgId: string | null;
}

export interface ChatTurn {
  role: "user" | "assistant" | "error";
  content: string;
  streaming?: boolean;
  toolCalls: ToolCallState[];
  skillActive: string[] | null;
  memoryRecalled: RecalledMemory[] | null;
  budget: { total: number; fraction: number; window: string } | null;
  /** thinking 增量累积（展示为可折叠摘要行） */
  thinking: string;
}

export interface RecalledMemory {
  id: string;
  score: number;
  strength: number;
}

export interface RunTimelineEntry {
  event_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface AppState {
  sessions: SessionRecord[];
  currentSessionId: string | null;
  /** 历史消息（进会话时从 /messages 拉取） */
  history: MessageView[];
  turns: ChatTurn[];
  streaming: boolean;
  droppedNotice: string | null;
  lastEventId: number | null;
  runs: RunRecord[];
  currentRunId: string | null;
  runEvents: RunEventView[];
  memoryTraces: MemoryTraceView[];
  memoryStats: Record<string, number> | null;
  status: RuntimeStatus | null;
  statusError: string | null;
  inspectorTab: "run" | "memory";
  user_id: string;
}

type Action =
  | { type: "sessions"; sessions: SessionRecord[] }
  | { type: "addSession"; session: SessionRecord }
  | { type: "removeSession"; sessionId: string }
  | { type: "selectSession"; sessionId: string | null; }
  | { type: "history"; messages: MessageView[] }
  | { type: "turnStart"; turn: ChatTurn }
  | { type: "turnPatch"; index: number; patch: Partial<ChatTurn> }
  | { type: "toolPatch"; turnIndex: number; toolIndex: number; patch: Partial<ToolCallState> }
  | { type: "streaming"; on: boolean }
  | { type: "lastEventId"; id: number | null }
  | { type: "dropped"; notice: string | null }
  | { type: "runs"; runs: RunRecord[] }
  | { type: "currentRun"; runId: string | null }
  | { type: "runEvents"; events: RunEventView[] }
  | { type: "memory"; traces: MemoryTraceView[]; stats: Record<string, number> | null }
  | { type: "status"; status: RuntimeStatus | null; error?: string | null }
  | { type: "inspectorTab"; tab: "run" | "memory" }
  | { type: "resetTurns" }
  /** 流事件进 reducer 累积（批内不丢 delta、越界不崩——review high/medium） */
  | { type: "streamEvent"; index: number; event: StreamEvent };

const initialState: AppState = {
  sessions: [],
  currentSessionId: null,
  history: [],
  turns: [],
  streaming: false,
  droppedNotice: null,
  lastEventId: null,
  runs: [],
  currentRunId: null,
  runEvents: [],
  memoryTraces: [],
  memoryStats: null,
  status: null,
  statusError: null,
  inspectorTab: "run",
  user_id: "default-user",
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "sessions":
      return { ...state, sessions: action.sessions };
    case "addSession":
      return {
        ...state,
        sessions: [...state.sessions, action.session],
      };
    case "removeSession":
      return {
        ...state,
        sessions: state.sessions.filter((s) => s.session_id !== action.sessionId),
      };
    case "selectSession":
      // review medium：事件 id 是 per-session 序列——切换必须清（否则新会话
      // 带旧 id 空间的 Last-Event-ID → 假"缺口超限"提示）
      return {
        ...state, currentSessionId: action.sessionId, turns: [], history: [],
        runs: [], runEvents: [], currentRunId: null,
        lastEventId: null, droppedNotice: null,
      };
    case "history":
      return { ...state, history: action.messages };
    case "turnStart":
      return { ...state, turns: [...state.turns, action.turn] };
    case "turnPatch": {
      const current = state.turns[action.index];
      if (!current) return state; // review high：会话切换后旧流补丁不打幽灵轮
      const turns = state.turns.slice();
      turns[action.index] = { ...current, ...action.patch };
      return { ...state, turns };
    }
    case "toolPatch": {
      const turn = state.turns[action.turnIndex];
      if (!turn) return state;
      const turns = state.turns.slice();
      const turnCopy = { ...turn };
      turnCopy.toolCalls = turnCopy.toolCalls.slice();
      turnCopy.toolCalls[action.toolIndex] = {
        ...turnCopy.toolCalls[action.toolIndex],
        ...action.patch,
      };
      turns[action.turnIndex] = turnCopy;
      return { ...state, turns };
    }
    case "streamEvent": {
      const turn = state.turns[action.index];
      if (!turn) return state; // 越界守卫（会话已切换/删除）
      const next = applyEventToTurn(turn, action.event);
      return next === turn ? state : { ...state, turns: replaceAt(state.turns, action.index, next) };
    }
    case "streaming":
      return { ...state, streaming: action.on };
    case "lastEventId":
      return { ...state, lastEventId: action.id };
    case "dropped":
      return { ...state, droppedNotice: action.notice };
    case "runs":
      return { ...state, runs: action.runs };
    case "currentRun":
      return { ...state, currentRunId: action.runId, runEvents: [] };
    case "runEvents":
      return { ...state, runEvents: action.events };
    case "memory":
      return { ...state, memoryTraces: action.traces, memoryStats: action.stats };
    case "status":
      return { ...state, status: action.status, statusError: action.error ?? null };
    case "inspectorTab":
      return { ...state, inspectorTab: action.tab };
    case "resetTurns":
      return { ...state, turns: [], droppedNotice: null, lastEventId: null };
    default:
      return state;
  }
}

function replaceAt<T>(arr: T[], index: number, value: T): T[] {
  const out = arr.slice();
  out[index] = value;
  return out;
}

/** 单个流事件 → turn 的纯函数累积（review medium：批内多帧共享同一 state
 * 快照会把彼此的 delta 抹掉——搬进 reducer 后每帧都基于最新 state）。 */
function applyEventToTurn(turn: ChatTurn, event: StreamEvent): ChatTurn {
  switch (event.type) {
    case "answer":
      return { ...turn, content: turn.content + (event.content || "") };
    case "thinking":
      return { ...turn, thinking: turn.thinking + (event.content || "") };
    case "skill_active": {
      // review medium：skill_active 实际载荷在 event.skills（content 可能为空串）
      let skills = event.skills ?? null;
      if (!skills && event.content) {
        try {
          const parsed = JSON.parse(event.content);
          if (Array.isArray(parsed)) skills = parsed;
        } catch {
          skills = [event.content];
        }
      }
      return { ...turn, skillActive: skills };
    }
    case "tool_start": {
      const tool: ToolCallState = {
        name: event.tool_name || "tool",
        args: event.tool_args || {},
        result: null,
        startedAt: Date.now(),
        finishedAt: null,
        failed: false,
        msgId: event.msg_id, // review medium：按 tool-call id 配对（同名并行不串卡）
      };
      return { ...turn, toolCalls: [...turn.toolCalls, tool] };
    }
    case "tool_end": {
      const toolCalls = turn.toolCalls.slice();
      // 先按 msg_id 精确配对；无 msg_id 时回退按名字找第一个未完成的
      let i = event.msg_id
        ? toolCalls.findIndex((t) => t.msgId === event.msg_id)
        : toolCalls.findIndex((t) => t.name === event.tool_name && t.result === null);
      if (i < 0 && event.tool_name) {
        i = toolCalls.findIndex((t) => t.name === event.tool_name && t.result === null);
      }
      if (i >= 0) {
        toolCalls[i] = {
          ...toolCalls[i],
          result: event.tool_result,
          finishedAt: Date.now(),
          failed: /error|fail/i.test(event.tool_result || ""),
        };
      }
      return { ...turn, toolCalls };
    }
    case "budget_update":
      return { ...turn, budget: event.budget || null };
    case "error":
      return { ...turn, content: turn.content + `\n\n[流内错误] ${event.content}` };
    case "done":
      return { ...turn, streaming: false };
    default:
      return turn;
  }
}

export interface AppActions {
  refreshSessions(): Promise<void>;
  createSession(): Promise<void>;
  selectSession(sessionId: string): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
  send(mode: "chat" | "research", message: string): Promise<void>;
  refreshRuns(): Promise<void>;
  openRun(runId: string): Promise<void>;
  refreshMemory(params?: {
    q?: string; type?: string; minStrength?: number; forgotten?: boolean; layer?: string;
  }): Promise<void>;
  refreshStatus(): Promise<void>;
  setInspectorTab(tab: "run" | "memory"): void;
}

const AppContext = createContext<{ state: AppState; actions: AppActions } | null>(null);

export function useApp(): { state: AppState; actions: AppActions } {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp 必须在 <AppProvider> 内使用");
  return ctx;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const api = useRef(new EngramAPI());
  const stateRef = useRef(state);
  stateRef.current = state;
  const streamAbort = useRef<AbortController | null>(null);

  const refreshSessions = useCallback(async () => {
    const sessions = await api.current
      .listSessions(stateRef.current.user_id)
      .catch(() => [] as SessionRecord[]);
    dispatch({ type: "sessions", sessions });
  }, []);

  const selectSession = useCallback(async (sessionId: string) => {
    // review medium：切换先中止在途流（旧流继续 dispatch 会写进 stale 索引）
    streamAbort.current?.abort();
    streamAbort.current = null;
    dispatch({ type: "selectSession", sessionId });
    const [messages, runs] = await Promise.all([
      api.current.messages(sessionId).catch(() => [] as MessageView[]),
      api.current.runs(sessionId).catch(() => [] as RunRecord[]),
    ]);
    // review medium：stale guard——快切 A→B 时 A 的晚到响应不得覆盖 B 的视图
    if (stateRef.current.currentSessionId !== sessionId) return;
    dispatch({ type: "history", messages });
    dispatch({ type: "runs", runs });
  }, []);

  const createSession = useCallback(async () => {
    // review medium：失败要可见（无提示的静默点击最迷惑）
    const record = await api.current
      .createSession(stateRef.current.user_id)
      .catch((err: Error) => {
        dispatch({ type: "dropped", notice: `新建会话失败：${err.message}` });
        return null;
      });
    if (!record) return;
    // reducer 内 append（闭包里读 stateRef 会拿到过期列表覆盖丢会话）
    dispatch({ type: "addSession", session: record });
    dispatch({ type: "selectSession", sessionId: record.session_id });
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    // 删的是当前会话 → 先中止流
    if (stateRef.current.currentSessionId === sessionId) {
      streamAbort.current?.abort();
      streamAbort.current = null;
    }
    await api.current.deleteSession(sessionId).catch(() => undefined);
    dispatch({ type: "removeSession", sessionId });
    if (stateRef.current.currentSessionId === sessionId) {
      dispatch({ type: "selectSession", sessionId: null });
    }
  }, []);

  const refreshRuns = useCallback(async () => {
    const sid = stateRef.current.currentSessionId;
    if (!sid) return;
    const runs = await api.current.runs(sid).catch(() => [] as RunRecord[]);
    dispatch({ type: "runs", runs });
  }, []);

  const openRun = useCallback(async (runId: string) => {
    dispatch({ type: "currentRun", runId });
    const data = await api.current
      .runEvents(runId)
      .catch(() => ({ run_id: runId, status: null, events: [] as RunEventView[] }));
    dispatch({ type: "runEvents", events: data.events });
  }, []);

  const refreshMemory = useCallback<AppActions["refreshMemory"]>(async (params) => {
    const [traces, stats] = await Promise.all([
      api.current
        .memoryTraces({ ...params, userId: stateRef.current.user_id })
        .catch(() => [] as MemoryTraceView[]),
      api.current
        .memoryStats(stateRef.current.user_id)
        .catch(() => null as Record<string, number> | null),
    ]);
    dispatch({ type: "memory", traces, stats });
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const status = await api.current.status();
      dispatch({ type: "status", status });
    } catch (err) {
      dispatch({ type: "status", status: null, error: String((err as Error).message) });
    }
  }, []);

  const send = useCallback(async (mode: "chat" | "research", message: string) => {
    const sid = stateRef.current.currentSessionId;
    if (!sid || stateRef.current.streaming) return;
    dispatch({
      type: "turnStart",
      turn: {
        role: "user",
        content: message,
        toolCalls: [],
        skillActive: null,
        memoryRecalled: null,
        budget: null,
        thinking: "",
      },
    });
    dispatch({
      type: "turnStart",
      turn: {
        role: "assistant",
        content: "",
        streaming: true,
        toolCalls: [],
        skillActive: null,
        memoryRecalled: null,
        budget: null,
        thinking: "",
      },
    });
    const assistantIndex = stateRef.current.turns.length + 1;
    dispatch({ type: "streaming", on: true });
    dispatch({ type: "dropped", notice: null });

    // review medium：可中止（切会话/删除时 abort，AbortError 单独归类不算错误）
    const controller = new AbortController();
    streamAbort.current = controller;

    try {
      await streamSSE(
        `/sessions/${sid}/${mode}`,
        { message },
        (frame) => {
          if (frame.id != null) {
            dispatch({ type: "lastEventId", id: frame.id });
          }
          const event = parseEventData<StreamEvent>(frame);
          if (!event) return;
          // review medium：事件累积走 reducer（批内多帧曾共享过期快照互相抹 delta）
          dispatch({ type: "streamEvent", index: assistantIndex, event });
        },
        {
          lastEventId: stateRef.current.lastEventId,
          signal: controller.signal,
          onDropped: (reason) => {
            dispatch({
              type: "dropped",
              notice: `部分事件丢失（${reason}），建议重开会话或运行`,
            });
          },
        },
      );
    } catch (err) {
      const aborted =
        controller.signal.aborted ||
        (err as Error).name === "AbortError";
      if (!aborted) {
        dispatch({
          type: "turnPatch",
          index: assistantIndex,
          patch: {
            streaming: false,
            content: (stateRef.current.turns[assistantIndex]?.content || "") +
              `\n\n[连接错误] ${(err as Error).message}`,
          },
        });
      }
    } finally {
      if (streamAbort.current === controller) streamAbort.current = null;
      dispatch({ type: "turnPatch", index: assistantIndex, patch: { streaming: false } });
      dispatch({ type: "streaming", on: false });
      // 流结束后刷新运行历史（run 投影可见；仅当仍是同一会话）
      if (stateRef.current.currentSessionId === sid) {
        refreshRuns().catch(() => undefined);
      }
    }
  }, [refreshRuns]);

  const setInspectorTab = useCallback((tab: "run" | "memory") => {
    dispatch({ type: "inspectorTab", tab });
  }, []);

  const actions = useMemo<AppActions>(
    () => ({
      refreshSessions, createSession, selectSession, deleteSession,
      send, refreshRuns, openRun, refreshMemory, refreshStatus, setInspectorTab,
    }),
    [refreshSessions, createSession, selectSession, deleteSession, send,
      refreshRuns, openRun, refreshMemory, refreshStatus, setInspectorTab],
  );

  return <AppContext.Provider value={{ state, actions }}>{children}</AppContext.Provider>;
}
