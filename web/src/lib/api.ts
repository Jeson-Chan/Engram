/** 网关 REST 客户端 — docs/api.md 契约的前端实现。 */

import type { CapabilityReport, MessageView, MemoryTraceView, RunEventView, RunRecord, RuntimeStatus, SkillInfo } from "./types";

export interface SessionRecord {
  session_id: string;
  thread_id: string;
  user_id: string;
  created_at: string;
  status: string;
  metadata: Record<string, unknown>;
}

/** DELETE /memory/traces 响应（specs/memory-clearance）。 */
export interface MemoryClearResult {
  grain: "trace" | "thread" | "user";
  preview?: boolean;
  /** preview=true 时的将删条数 */
  count?: number;
  /** 实际删除条数 */
  deleted?: number;
  trace_ids?: string[];
  trace_id?: string;
  user_id?: string;
  thread_id?: string | null;
}

async function jsonOrThrow<T>(resp: Response, fallback: string): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new APIError(resp.status, text || fallback);
  }
  return resp.json() as Promise<T>;
}

export class APIError extends Error {
  constructor(public status: number, public detail: string) {
    super(`API ${status}: ${detail.slice(0, 200)}`);
  }
}

export class EngramAPI {
  // （review medium：summarizeSession 死代码已删——SessionRecord 直达 UI，
  // 伪造 message_count/memory_count 占位数据反而误导。）
  constructor(private base = "") {}

  // ---- sessions ----

  listSessions(userId?: string): Promise<SessionRecord[]> {
    const q = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return fetch(`${this.base}/sessions${q}`).then((r) =>
      jsonOrThrow<SessionRecord[]>(r, "list sessions failed"),
    );
  }

  createSession(
    userId = "default-user",
    metadata: Record<string, unknown> = {},
  ): Promise<SessionRecord> {
    return fetch(`${this.base}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, metadata }),
    }).then((r) => jsonOrThrow<SessionRecord>(r, "create session failed"));
  }

  deleteSession(sessionId: string): Promise<void> {
    return fetch(`${this.base}/sessions/${sessionId}`, { method: "DELETE" }).then((r) => {
      if (r.status === 404) throw new APIError(404, "session not found");
      if (!r.ok) throw new APIError(r.status, "delete failed");
    });
  }

  /** 重命名（PATCH /sessions/{id}）——返回更新后的会话记录。 */
  renameSession(sessionId: string, title: string): Promise<SessionRecord> {
    return fetch(`${this.base}/sessions/${sessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).then((r) => jsonOrThrow<SessionRecord>(r, "rename failed"));
  }

  // ---- history ----

  messages(sessionId: string, limit = 50, offset = 0): Promise<MessageView[]> {
    return fetch(
      `${this.base}/sessions/${sessionId}/messages?limit=${limit}&offset=${offset}`,
    ).then((r) => jsonOrThrow<MessageView[]>(r, "load messages failed"));
  }

  runs(sessionId: string): Promise<RunRecord[]> {
    return fetch(`${this.base}/sessions/${sessionId}/runs`).then((r) =>
      jsonOrThrow<RunRecord[]>(r, "load runs failed"),
    );
  }

  runEvents(runId: string): Promise<{ run_id: string; status: string | null; events: RunEventView[] }> {
    return fetch(`${this.base}/runs/${runId}/events?limit=500`).then((r) =>
      jsonOrThrow(r, "load run events failed"),
    );
  }

  runReportUrl(runId: string): string {
    return `${this.base}/runs/${runId}/report`;
  }

  // ---- memory ----

  memoryStats(userId?: string): Promise<Record<string, number>> {
    const q = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return fetch(`${this.base}/memory/stats${q}`).then((r) =>
      jsonOrThrow<Record<string, number>>(r, "load memory stats failed"),
    );
  }

  memoryTraces(params: {
    userId?: string;
    q?: string;
    type?: string;
    minStrength?: number;
    forgotten?: boolean;
    layer?: string;
    limit?: number;
  } = {}): Promise<MemoryTraceView[]> {
    const search = new URLSearchParams();
    if (params.userId) search.set("user_id", params.userId);
    if (params.q) search.set("q", params.q);
    if (params.type) search.set("type", params.type);
    if (params.minStrength != null && params.minStrength > 0)
      search.set("min_strength", String(params.minStrength));
    if (params.forgotten != null) search.set("forgotten", String(params.forgotten));
    if (params.layer) search.set("layer", params.layer);
    search.set("limit", String(params.limit ?? 200));
    return fetch(`${this.base}/memory/traces?${search}`).then((r) =>
      jsonOrThrow<MemoryTraceView[]>(r, "load memory traces failed"),
    );
  }

  /**
   * 记忆清除（DELETE /memory/traces，memory-management-ui）。
   * - 单条：{ traceId }；thread 粒度：{ userId, threadId }；user 粒度：{ userId }
   * - preview=true 只返回将删计数（与删除同一谓词），不产生副作用
   */
  memoryClear(
    params: { traceId?: string; userId?: string; threadId?: string },
    preview = false,
  ): Promise<MemoryClearResult> {
    const search = new URLSearchParams();
    if (params.traceId) search.set("trace_id", params.traceId);
    if (params.userId) search.set("user_id", params.userId);
    if (params.threadId) search.set("thread_id", params.threadId);
    if (preview) search.set("preview", "true");
    return fetch(`${this.base}/memory/traces?${search}`, { method: "DELETE" }).then(
      (r) => jsonOrThrow<MemoryClearResult>(r, "memory clear failed"),
    );
  }

  // ---- status ----

  status(): Promise<RuntimeStatus> {
    return fetch(`${this.base}/status`).then((r) =>
      jsonOrThrow<RuntimeStatus>(r, "load status failed"),
    );
  }

  // ---- skills（web-skill-override）----

  /** 激活 skill 列表（含 enabled）。skill 模块未启用时网关返回空数组。 */
  listSkills(): Promise<SkillInfo[]> {
    return fetch(`${this.base}/skills`).then((r) =>
      jsonOrThrow<SkillInfo[]>(r, "load skills failed"),
    );
  }

  /** 启用/禁用单个 skill（运行时持久，跨重启）。未知名 404 / 模块未启用 503。 */
  setSkillEnabled(skillId: string, enabled: boolean): Promise<{ skill_id: string; enabled: boolean }> {
    return fetch(`${this.base}/skills/${encodeURIComponent(skillId)}/enabled`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).then((r) =>
      jsonOrThrow<{ skill_id: string; enabled: boolean }>(r, "set skill enabled failed"),
    );
  }

  // ---- 运行配置（web-config-surface）----

  /** 应用模型/模式变更（网关全局；作用于所有会话的后续运行）。 */
  applyConfig(payload: { provider?: string; model?: string; expert_mode?: boolean }): Promise<{
    model: string | null; provider: string | null; mode: string | null; reloaded: boolean;
  }> {
    return fetch(`${this.base}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) =>
      jsonOrThrow<{ model: string | null; provider: string | null; mode: string | null; reloaded: boolean }>(
        r, "apply config failed",
      ),
    );
  }

  /** 重载 MCP 工具（重建 graph）。模块未启用 → 503。 */
  reloadMcp(): Promise<{ reloaded: boolean; mcp: Array<Record<string, unknown>> }> {
    return fetch(`${this.base}/mcp/reload`, { method: "POST" }).then((r) =>
      jsonOrThrow<{ reloaded: boolean; mcp: Array<Record<string, unknown>> }>(r, "reload mcp failed"),
    );
  }

  // ---- 报告生成（surface-parity，web 版 TUI /report）----

  /** 从会话 thread 生成报告（同步执行；返回 artifact 路径与全文）。 */
  generateReport(sessionId: string, topic?: string): Promise<{
    artifact_path: string | null; final_report: string;
  }> {
    return fetch(`${this.base}/sessions/${encodeURIComponent(sessionId)}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: topic ?? null }),
    }).then((r) =>
      jsonOrThrow<{ artifact_path: string | null; final_report: string }>(r, "generate report failed"),
    );
  }

  // ---- 运行中插话（real-steer）----

  /** 流式期间向活跃运行插话（下一模型步注入）。无活跃运行 → 409。 */
  steer(sessionId: string, message: string): Promise<{ accepted: boolean; thread_id: string }> {
    return fetch(`${this.base}/sessions/${encodeURIComponent(sessionId)}/steer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }).then((r) =>
      jsonOrThrow<{ accepted: boolean; thread_id: string }>(r, "steer failed"),
    );
  }

  /** 能力三态矩阵（engram doctor 同源；探测含网络检查，秒级延迟）。 */
  capabilities(): Promise<CapabilityReport> {
    return fetch(`${this.base}/capabilities`).then((r) =>
      jsonOrThrow<CapabilityReport>(r, "load capabilities failed"),
    );
  }
}
