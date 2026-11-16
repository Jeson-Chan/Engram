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
import { parseEventData, streamSSE, type SSEFrame } from "./lib/sse";
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
}

export interface ChatTurn {
  role: "user" | "assistant" | "error";
  content: string;
  streaming?: boolean;
  toolCalls: ToolCallState[];
  skillActive: string[] | null;
  memoryRecalled: RecalledMemory[] | null;
  budget: { total: number; fraction: number; window: string } | null;
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
  | { type: "resetTurns" };

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
    case "selectSession":
      return { ...state, currentSessionId: action.sessionId, turns: [], history: [], runs: [], runEvents: [], currentRunId: null };
    case "history":
      return { ...state, history: action.messages };
    case "turnStart":
      return { ...state, turns: [...state.turns, action.turn] };
    case "turnPatch": {
      const turns = state.turns.slice();
      turns[action.index] = { ...turns[action.index], ...action.patch };
      return { ...state, turns };
    }
    case "toolPatch": {
      const turns = state.turns.slice();
      const turn = { ...turns[action.turnIndex] };
      turn.toolCalls = turn.toolCalls.slice();
      turn.toolCalls[action.toolIndex] = {
        ...turn.toolCalls[action.toolIndex],
        ...action.patch,
      };
      turns[action.turnIndex] = turn;
      return { ...state, turns };
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

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const api = useRef(new EngramAPI());
  const stateRef = useRef(state);
  stateRef.current = state;

  const refreshSessions = useCallback(async () => {
    const sessions = await api.current
      .listSessions(stateRef.current.user_id)
      .catch(() => [] as SessionRecord[]);
    dispatch({ type: "sessions", sessions });
  }, []);

  const selectSession = useCallback(async (sessionId: string) => {
    dispatch({ type: "selectSession", sessionId });
    const [messages, runs] = await Promise.all([
      api.current.messages(sessionId).catch(() => [] as MessageView[]),
      api.current.runs(sessionId).catch(() => [] as RunRecord[]),
    ]);
    dispatch({ type: "history", messages });
    dispatch({ type: "runs", runs });
  }, []);

  const createSession = useCallback(async () => {
    const record = await api.current.createSession(stateRef.current.user_id);
    dispatch({ type: "selectSession", sessionId: record.session_id });
    dispatch({
      type: "sessions",
      sessions: [...stateRef.current.sessions, record],
    });
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    await api.current.deleteSession(sessionId).catch(() => undefined);
    const sessions = stateRef.current.sessions.filter(
      (s) => s.session_id !== sessionId,
    );
    dispatch({ type: "sessions", sessions });
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
      },
    });
    const assistantIndex = stateRef.current.turns.length + 1;
    dispatch({ type: "streaming", on: true });
    dispatch({ type: "dropped", notice: null });

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
          applyStreamEvent(event, assistantIndex, dispatch, stateRef);
        },
        {
          lastEventId: stateRef.current.lastEventId,
          onDropped: (reason) => {
            dispatch({
              type: "dropped",
              notice: `部分事件丢失（${reason}），建议重开会话或运行`,
            });
          },
        },
      );
    } catch (err) {
      dispatch({
        type: "turnPatch",
        index: assistantIndex,
        patch: { streaming: false, content: (stateRef.current.turns[assistantIndex]?.content || "") + `\n\n[连接错误] ${(err as Error).message}` },
      });
    } finally {
      dispatch({ type: "turnPatch", index: assistantIndex, patch: { streaming: false } });
      dispatch({ type: "streaming", on: false });
      // 流结束后刷新运行历史（run 投影可见）
      refreshRuns().catch(() => undefined);
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

type Dispatch = React.Dispatch<Action>;

function applyStreamEvent(
  event: StreamEvent,
  assistantIndex: number,
  dispatch: Dispatch,
  stateRef: React.MutableRefObject<AppState>,
) {
  const turn = stateRef.current.turns[assistantIndex];
  const patch: Partial<ChatTurn> = {};
  switch (event.type) {
    case "answer":
      patch.content = (turn?.content || "") + (event.content || "");
      break;
    case "thinking":
      // 思考增量暂存（轻渲染：拼在折屉里，本实现并入 content 前缀区）
      break;
    case "skill_active":
      try {
        patch.skillActive = JSON.parse(event.content || "[]");
      } catch {
        patch.skillActive = [event.content];
      }
      break;
    case "tool_start": {
      const tool: ToolCallState = {
        name: event.tool_name || "tool",
        args: event.tool_args || {},
        result: null,
        startedAt: Date.now(),
        finishedAt: null,
        failed: false,
      };
      const toolCalls = [...(turn?.toolCalls || []), tool];
      patch.toolCalls = toolCalls;
      break;
    }
    case "tool_end": {
      const toolCalls = (turn?.toolCalls || []).slice();
      for (let i = toolCalls.length - 1; i >= 0; i -= 1) {
        if (toolCalls[i].name === event.tool_name && toolCalls[i].result === null) {
          toolCalls[i] = {
            ...toolCalls[i],
            result: event.tool_result,
            finishedAt: Date.now(),
            failed: /error|fail/i.test(event.tool_result || ""),
          };
          break;
        }
      }
      patch.toolCalls = toolCalls;
      break;
    }
    case "budget_update":
      patch.budget = event.budget || null;
      break;
    case "error":
      patch.content = (turn?.content || "") + `\n\n[流内错误] ${event.content}`;
      break;
    case "done":
      patch.streaming = false;
      break;
    default:
      break;
  }
  if (Object.keys(patch).length > 0) {
    dispatch({ type: "turnPatch", index: assistantIndex, patch });
  }
}
