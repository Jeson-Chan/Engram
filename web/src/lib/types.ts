/** 与后端 engram/backend/app/gateway/views.py 对齐的客户端类型。 */

export interface SessionSummary {
  session_id: string;
  thread_id: string;
  title: string;
  user_id: string;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  memory_count: number;
  last_run_status: string | null;
}

export interface ToolCallView {
  name: string;
  args: Record<string, unknown>;
  id: string | null;
}

export interface MessageView {
  role: string;
  content: string;
  tool_calls: ToolCallView[];
  msg_id: string | null;
  created_at: string | null;
}

export interface MemoryTraceView {
  id: string;
  content: string;
  type: string;
  strength: number;
  decay_rate: number;
  access_count: number;
  source: string | null;
  created_at: string | null;
  forgotten: boolean;
  layer: string | null; // "hot" | "cold" | null
}

export interface RunEventView {
  event_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface RuntimeStatus {
  model: string | null;
  provider: string | null;
  mode: string | null;
  skills: Array<Record<string, unknown>>;
  mcp: Array<Record<string, unknown>>;
  sandbox: Record<string, unknown>;
}

/** 能力三态矩阵行（engram doctor 同源，GET /capabilities；无密钥）。 */
export interface CapabilityRow {
  key: string;
  label: string;
  state: "on" | "off" | "broken";
  detail: string;
  fix: string;
}

export interface ConnectivityRow {
  key: string;
  label: string;
  state: "ok" | "fail" | "skipped";
  detail: string;
}

export interface CapabilityReport {
  deployment?: "docker" | "venv";
  capabilities: CapabilityRow[];
  connectivity: ConnectivityRow[];
  has_broken?: boolean;
}

export interface RunRecord {
  run_id: string;
  thread_id: string;
  user_id: string | null;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  model_name: string | null;
  error: string | null;
  total_tokens: number | null;
  report_path: string | null;
}

/** SSE 流事件（docs/event-semantics.md 的机器可读契约）。 */
export interface StreamEvent {
  type: string;
  content: string;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: string | null;
  msg_id: string | null;
  /** skill_active 事件实际携带的 skill 名列表（content 可能为空串——
   * review medium：只解析 content 会恒得空列表）。 */
  skills?: string[];
  budget?: {
    total: number;
    fraction: number;
    window: string;
  } | null;
}
