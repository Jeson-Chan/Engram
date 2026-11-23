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
  CapabilityReport,
  MemoryTraceView,
  MessageView,
  RunEventView,
  RunRecord,
  RuntimeStatus,
  SkillInfo,
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

export interface MemFilters {
  q: string;
  type: string; // "" = 全部
  layer: string; // "" = 全部
  minStrength: number;
}

export interface MemPartition {
  userId: string;
  threadId: string | null; // null = 整个 user
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
  /** 能力矩阵（doctor 同源；切到"能力" tab 时按需拉取） */
  capabilities: CapabilityReport | null;
  capabilitiesError: string | null;
  inspectorTab: "run" | "capabilities" | "configs";
  user_id: string;
  /** 主区模式（memory-management-ui）：对话工作台 / 全宽记忆管理页 */
  mainView: "chat" | "memory";
  /** 记忆页筛选（切走再切回不丢） */
  memFilters: MemFilters;
  /** 记忆页分区选择（null = 不按分区过滤） */
  memPartition: MemPartition | null;
  /** 记忆列表多选（trace id 集合） */
  memSelected: string[];
  /** 记忆未配置（503）→ 空态，删除操作不可用 */
  memoryUnavailable: boolean;
  /** skill 管理列表（GET /skills，web-skill-override；空数组 = 未启用或未加载） */
  skills: SkillInfo[];
  skillsError: string | null;
  /** 当前会话 skill override（请求级携带，刷新即清——design D1） */
  skillOverride: string[];
  /** 会话级运行参数（runtime-knobs；null/0 = auto，请求级携带） */
  knobs: RuntimeKnobs;
  /** Configs 面板草稿（web-config-surface）：仅编辑态，应用前不改变运行时 */
  configDraft: ConfigDraft;
  /** 对话流展示 Thought 折叠行（Configs 显示开关；默认开） */
  thinkingVisible: boolean;
  /** Configs 面板 toast（"已生效!" / 失败项） */
  configToast: { kind: "ok" | "err"; text: string } | null;
}

/** Configs 草稿：undefined = 未改；显式 null = 清除为 auto。 */
export interface ConfigDraft {
  skills?: Record<string, boolean>;
  override?: string[];
  maxLoopSteps?: number | null;
  reasoningEffort?: "low" | "medium" | "high" | null;
  contextWindow?: number | null;
  provider?: string | null;
  model?: string | null;
  mode?: "expert" | "lightweight" | null;
  thinkingVisible?: boolean;
}

export interface RuntimeKnobs {
  maxLoopSteps: number | null;
  reasoningEffort: "low" | "medium" | "high" | null;
  contextWindow: number | null;
}

type Action =
  | { type: "sessions"; sessions: SessionRecord[] }
  | { type: "addSession"; session: SessionRecord }
  | { type: "renameSession"; sessionId: string; title: string }
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
  | { type: "memoryUnavailable"; on: boolean }
  | { type: "skills"; skills: SkillInfo[]; error?: string | null }
  | { type: "skillOverride"; names: string[] }
  | { type: "knobs"; patch: Partial<RuntimeKnobs> }
  | { type: "configDraft"; patch: Partial<ConfigDraft> }
  | { type: "configDraftReset" }
  | { type: "configToast"; toast: { kind: "ok" | "err"; text: string } | null }
  | { type: "thinking"; value: boolean }
  | { type: "status"; status: RuntimeStatus | null; error?: string | null }
  | { type: "capabilities"; report: CapabilityReport | null; error?: string | null }
  | { type: "inspectorTab"; tab: "run" | "capabilities" | "configs" }
  | { type: "mainView"; view: "chat" | "memory" }
  | { type: "memFilters"; patch: Partial<MemFilters> }
  | { type: "memPartition"; partition: MemPartition | null }
  | { type: "memSelected"; ids: string[] }
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
  capabilities: null,
  capabilitiesError: null,
  inspectorTab: "run",
  user_id: "default-user",
  mainView: "chat",
  memFilters: { q: "", type: "", layer: "", minStrength: 0 },
  memPartition: null,
  memSelected: [],
  memoryUnavailable: false,
  skills: [],
  skillsError: null,
  skillOverride: [],
  knobs: { maxLoopSteps: null, reasoningEffort: null, contextWindow: null },
  configDraft: {},
  thinkingVisible: true,
  configToast: null,
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
    case "renameSession":
      return {
        ...state,
        sessions: state.sessions.map((s) =>
          s.session_id === action.sessionId
            ? { ...s, metadata: { ...s.metadata, title: action.title } }
            : s,
        ),
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
    case "memoryUnavailable":
      return { ...state, memoryUnavailable: action.on };
    case "skills":
      return { ...state, skills: action.skills, skillsError: action.error ?? null };
    case "skillOverride":
      return { ...state, skillOverride: action.names };
    case "knobs":
      return { ...state, knobs: { ...state.knobs, ...action.patch } };
    case "configDraft":
      return { ...state, configDraft: { ...state.configDraft, ...action.patch } };
    case "configDraftReset":
      return { ...state, configDraft: {} };
    case "configToast":
      return { ...state, configToast: action.toast };
    case "thinking":
      return { ...state, thinkingVisible: action.value };
    case "mainView":
      return { ...state, mainView: action.view };
    case "memFilters":
      return { ...state, memFilters: { ...state.memFilters, ...action.patch } };
    case "memPartition":
      // 分区切换清空多选（选中集合属于旧分区视图）
      return { ...state, memPartition: action.partition, memSelected: [] };
    case "memSelected":
      return { ...state, memSelected: action.ids };
    case "status":
      return { ...state, status: action.status, statusError: action.error ?? null };
    case "capabilities":
      return { ...state, capabilities: action.report, capabilitiesError: action.error ?? null };
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
  renameSession(sessionId: string, title: string): Promise<void>;
  send(mode: "chat" | "research", message: string): Promise<void>;
  refreshRuns(): Promise<void>;
  openRun(runId: string): Promise<void>;
  refreshMemory(params?: {
    q?: string; type?: string; minStrength?: number; forgotten?: boolean; layer?: string;
  }): Promise<void>;
  refreshStatus(): Promise<void>;
  refreshCapabilities(): Promise<void>;
  setInspectorTab(tab: "run" | "capabilities" | "configs"): void;
  setConfigDraft(patch: Partial<ConfigDraft>): void;
  applyConfig(): Promise<boolean>;
  clearConfigToast(): void;
  reloadMcp(): Promise<boolean>;
  setMainView(view: "chat" | "memory"): void;
  setMemFilters(patch: Partial<MemFilters>): void;
  setMemPartition(partition: MemPartition | null): void;
  toggleMemSelected(traceId: string): void;
  setMemSelected(ids: string[]): void;
  deleteMemoryTrace(traceId: string): Promise<void>;
  clearMemoryPartition(userId: string, threadId?: string): Promise<void>;
  previewMemoryPartition(userId: string, threadId?: string): Promise<number>;
  openMemoryForThread(threadId: string): void;
  openSessionFromMemory(threadId: string | null): Promise<void>;
  refreshSkills(): Promise<void>;
  setSkillOverride(names: string[]): void;
  setSkillEnabled(skillId: string, enabled: boolean): Promise<boolean>;
  setKnobs(patch: Partial<RuntimeKnobs>): void;
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

  const renameSession = useCallback(async (sessionId: string, title: string) => {
    // 乐观更新：先改本地；失败回滚原值 + dropped 提示（与 delSession 错误模式一致）
    const original = stateRef.current.sessions.find((s) => s.session_id === sessionId);
    dispatch({ type: "renameSession", sessionId, title });
    try {
      await api.current.renameSession(sessionId, title);
    } catch (err) {
      if (original) {
        dispatch({
          type: "renameSession",
          sessionId,
          title: String(original.metadata?.title ?? ""),
        });
      }
      dispatch({ type: "dropped", notice: `重命名失败：${(err as Error).message}` });
    }
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

  const refreshMemory = useCallback<AppActions["refreshMemory"]>(async () => {
    // 全量拉取（不按筛选/分区过滤，树与列表都在前端聚合——design.md 决策 6）
    try {
      const [traces, stats] = await Promise.all([
        api.current.memoryTraces({ userId: stateRef.current.user_id, limit: 500 }),
        api.current.memoryStats(stateRef.current.user_id),
      ]);
      dispatch({ type: "memory", traces, stats });
      dispatch({ type: "memoryUnavailable", on: false });
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 503) {
        dispatch({ type: "memoryUnavailable", on: true });
      } else {
        dispatch({ type: "memory", traces: [], stats: null });
      }
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const status = await api.current.status();
      dispatch({ type: "status", status });
    } catch (err) {
      dispatch({ type: "status", status: null, error: String((err as Error).message) });
    }
  }, []);

  const refreshCapabilities = useCallback(async () => {
    try {
      const report = await api.current.capabilities();
      dispatch({ type: "capabilities", report });
    } catch (err) {
      dispatch({ type: "capabilities", report: null, error: String((err as Error).message) });
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

    // runtime-knobs：仅设置了的旋钮才进请求体（缺省键 = 服务端默认行为）
    const body: Record<string, unknown> = {
      message,
      skill_override: stateRef.current.skillOverride,
    };
    const knobs = stateRef.current.knobs;
    if (knobs.maxLoopSteps) body.max_loop_steps = knobs.maxLoopSteps;
    if (knobs.reasoningEffort) body.reasoning_effort = knobs.reasoningEffort;
    if (knobs.contextWindow) body.context_window = knobs.contextWindow;

    try {
      await streamSSE(
        `/sessions/${sid}/${mode}`,
        body,
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

  const setInspectorTab = useCallback((tab: "run" | "capabilities" | "configs") => {
    dispatch({ type: "inspectorTab", tab });
  }, []);

  // ---- 记忆管理页（memory-management-ui） ----

  const setMainView = useCallback((view: "chat" | "memory") => {
    dispatch({ type: "mainView", view });
    if (view === "memory") refreshMemory().catch(() => undefined);
  }, [refreshMemory]);

  const setMemFilters = useCallback((patch: Partial<MemFilters>) => {
    dispatch({ type: "memFilters", patch });
  }, []);

  const setMemPartition = useCallback((partition: MemPartition | null) => {
    dispatch({ type: "memPartition", partition });
  }, []);

  const toggleMemSelected = useCallback((traceId: string) => {
    const cur = stateRef.current.memSelected;
    const ids = cur.includes(traceId)
      ? cur.filter((id) => id !== traceId)
      : [...cur, traceId];
    dispatch({ type: "memSelected", ids });
  }, []);

  const setMemSelected = useCallback((ids: string[]) => {
    dispatch({ type: "memSelected", ids });
  }, []);

  const deleteMemoryTrace = useCallback(async (traceId: string) => {
    try {
      await api.current.memoryClear({ traceId });
    } catch (err) {
      dispatch({ type: "dropped", notice: `删除失败：${(err as Error).message}` });
      return;
    }
    dispatch({
      type: "memSelected",
      ids: stateRef.current.memSelected.filter((id) => id !== traceId),
    });
    await refreshMemory();
  }, [refreshMemory]);

  const clearMemoryPartition = useCallback(
    async (userId: string, threadId?: string) => {
      try {
        await api.current.memoryClear({ userId, threadId });
      } catch (err) {
        dispatch({ type: "dropped", notice: `清除失败：${(err as Error).message}` });
        return;
      }
      dispatch({ type: "memSelected", ids: [] });
      await refreshMemory();
    },
    [refreshMemory],
  );

  const previewMemoryPartition = useCallback(
    async (userId: string, threadId?: string): Promise<number> => {
      try {
        const result = await api.current.memoryClear({ userId, threadId }, true);
        return result.count ?? 0;
      } catch {
        return -1; // 预览失败（调用方禁用确认按钮）
      }
    },
    [],
  );

  /** 会话模式 → 记忆模式：定位到该会话的 thread 分区。 */
  const openMemoryForThread = useCallback(
    (threadId: string) => {
      dispatch({
        type: "memPartition",
        partition: { userId: stateRef.current.user_id, threadId },
      });
      dispatch({ type: "mainView", view: "memory" });
      refreshMemory().catch(() => undefined);
    },
    [refreshMemory],
  );

  /** 记忆模式 → 会话模式：按 thread 找会话并选中（找不到仅切回）。 */
  const openSessionFromMemory = useCallback(
    async (threadId: string | null) => {
      dispatch({ type: "mainView", view: "chat" });
      if (!threadId) return;
      const session = stateRef.current.sessions.find((s) => s.thread_id === threadId);
      if (session) {
        await selectSession(session.session_id);
      } else {
        dispatch({ type: "dropped", notice: `未找到 thread ${threadId} 对应的会话` });
      }
    },
    [selectSession],
  );

  // ---- skill 管理（web-skill-override）----

  const refreshSkills = useCallback(async () => {
    try {
      const skills = await api.current.listSkills();
      dispatch({ type: "skills", skills });
    } catch (err) {
      dispatch({ type: "skills", skills: [], error: String((err as Error).message) });
    }
  }, []);

  /** 会话级 override：请求级携带、刷新即清（design D1）。空数组 = 清除。 */
  const setSkillOverride = useCallback((names: string[]) => {
    dispatch({ type: "skillOverride", names });
  }, []);

  /** 会话级运行参数（runtime-knobs）：null = auto；随每次 chat 请求携带。 */
  const setKnobs = useCallback((patch: Partial<RuntimeKnobs>) => {
    dispatch({ type: "knobs", patch });
  }, []);

  // ---- Configs 草稿与应用（web-config-surface）----

  const setConfigDraft = useCallback((patch: Partial<ConfigDraft>) => {
    dispatch({ type: "configDraft", patch });
  }, []);

  const clearConfigToast = useCallback(() => {
    dispatch({ type: "configToast", toast: null });
  }, []);

  /** 一次提交全部草稿：技能启停 diff → 模型/模式 → 本地状态（override/旋钮/思考）。
   *  成功清空草稿 + "已生效!"；失败保留草稿并提示失败项。 */
  const applyConfig = useCallback(async (): Promise<boolean> => {
    const s = stateRef.current;
    const draft = s.configDraft;
    try {
      // 1) 技能启停：草稿与已加载的 diff
      if (draft.skills) {
        for (const skill of s.skills) {
          const want = draft.skills[skill.skill_id];
          if (typeof want === "boolean" && want !== skill.enabled) {
            await api.current.setSkillEnabled(skill.skill_id, want);
          }
        }
        await refreshSkills();
      }
      // 2) 模型/模式（网关全局；作用于所有会话的后续运行）
      if (draft.provider) {
        await api.current.applyConfig({
          provider: draft.provider,
          model: draft.model || undefined,
          expert_mode: draft.mode == null ? undefined : draft.mode === "expert",
        });
        await refreshStatus();
      } else if (draft.mode != null) {
        await api.current.applyConfig({ expert_mode: draft.mode === "expert" });
        await refreshStatus();
      }
      // 3) 本地状态（override / 三旋钮 / 思考显示）
      if (draft.override) {
        dispatch({ type: "skillOverride", names: draft.override });
      }
      const knobPatch: Partial<RuntimeKnobs> = {};
      if (draft.maxLoopSteps !== undefined) knobPatch.maxLoopSteps = draft.maxLoopSteps;
      if (draft.reasoningEffort !== undefined) knobPatch.reasoningEffort = draft.reasoningEffort;
      if (draft.contextWindow !== undefined) knobPatch.contextWindow = draft.contextWindow;
      if (Object.keys(knobPatch).length > 0) {
        dispatch({ type: "knobs", patch: knobPatch });
      }
      if (draft.thinkingVisible !== undefined) {
        dispatch({ type: "thinking", value: draft.thinkingVisible });
      }
      dispatch({ type: "configDraftReset" });
      dispatch({ type: "configToast", toast: { kind: "ok", text: "已生效!" } });
      return true;
    } catch (err) {
      dispatch({
        type: "configToast",
        toast: { kind: "err", text: `应用失败：${(err as Error).message}` },
      });
      return false;
    }
  }, [refreshSkills, refreshStatus]);

  /** 重载 MCP（独立按钮，非 apply 链）。 */
  const reloadMcp = useCallback(async (): Promise<boolean> => {
    try {
      await api.current.reloadMcp();
      await refreshStatus();
      dispatch({ type: "configToast", toast: { kind: "ok", text: "MCP 已重载" } });
      return true;
    } catch (err) {
      dispatch({
        type: "configToast",
        toast: { kind: "err", text: `MCP 重载失败：${(err as Error).message}` },
      });
      return false;
    }
  }, [refreshStatus]);

  /** 启停 + 刷新列表；返回成功与否（失败由面板提示，调用方回滚 UI）。 */
  const setSkillEnabled = useCallback(async (skillId: string, enabled: boolean) => {
    try {
      await api.current.setSkillEnabled(skillId, enabled);
      await refreshSkills();
      return true;
    } catch (err) {
      dispatch({ type: "skills", skills: stateRef.current.skills, error: String((err as Error).message) });
      return false;
    }
  }, [refreshSkills]);

  const actions = useMemo<AppActions>(
    () => ({
      refreshSessions, createSession, selectSession, deleteSession, renameSession,
      send, refreshRuns, openRun, refreshMemory, refreshStatus, refreshCapabilities, setInspectorTab,
      setMainView, setMemFilters, setMemPartition, toggleMemSelected,
      setMemSelected, deleteMemoryTrace, clearMemoryPartition,
      previewMemoryPartition, openMemoryForThread, openSessionFromMemory,
      refreshSkills, setSkillOverride, setSkillEnabled, setKnobs,
      setConfigDraft, applyConfig, clearConfigToast, reloadMcp,
    }),
    [refreshSessions, createSession, selectSession, deleteSession, renameSession, send,
      refreshRuns, openRun, refreshMemory, refreshStatus, refreshCapabilities, setInspectorTab,
      setMainView, setMemFilters, setMemPartition, toggleMemSelected,
      setMemSelected, deleteMemoryTrace, clearMemoryPartition,
      previewMemoryPartition, openMemoryForThread, openSessionFromMemory,
      refreshSkills, setSkillOverride, setSkillEnabled, setKnobs,
      setConfigDraft, applyConfig, clearConfigToast, reloadMcp],
  );

  return <AppContext.Provider value={{ state, actions }}>{children}</AppContext.Provider>;
}
