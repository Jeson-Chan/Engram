/** 网关 REST 客户端 — docs/api.md 契约的前端实现。 */

import type {
  MessageView,
  MemoryTraceView,
  RunEventView,
  RunRecord,
  RuntimeStatus,
  SessionSummary,
} from "./types";

export interface SessionRecord {
  session_id: string;
  thread_id: string;
  user_id: string;
  created_at: string;
  status: string;
  metadata: Record<string, unknown>;
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

  // ---- status ----

  status(): Promise<RuntimeStatus> {
    return fetch(`${this.base}/status`).then((r) =>
      jsonOrThrow<RuntimeStatus>(r, "load status failed"),
    );
  }
}

export function summarizeSession(record: SessionRecord): SessionSummary {
  return {
    session_id: record.session_id,
    thread_id: record.thread_id,
    title: String(record.metadata?.title || `Session ${record.session_id.slice(0, 8)}`),
    user_id: record.user_id,
    created_at: record.created_at,
    updated_at: record.created_at,
    message_count: 0,
    memory_count: 0,
    last_run_status: null,
  };
}
