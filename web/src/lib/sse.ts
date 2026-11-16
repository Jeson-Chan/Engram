/** POST SSE 客户端解析器 — docs/event-semantics.md 的前端实现。
 *
 * 浏览器原生 EventSource 只支持 GET；/chat /research 是 POST SSE，
 * 用 fetch + ReadableStream 手动解析（design.md 决策 2）。
 *
 * 契约（由 src/lib/__tests__/sse.test.ts 引用文档示例验证）：
 * - 帧格式：`id: N` / `event: type` / `data: {json}`，空行分帧
 * - 换行容忍 \n 与 \r\n；分块边界任意（跨 chunk 的帧也正确解析）
 * - 每帧回调 (event, id, data)；`data:` 后空格剥一个
 * - 重连：streamSSE(events, {lastEventId}) 携带 Last-Event-ID 请求头
 * - dropped：响应头 X-Engram-Events-Dropped 或流内 error(
 *   "resume gap exceeded buffer capacity") → onDropped 明示，
 *   不静默拼接
 */

export interface SSEOptions {
  /** 断线重连时上报的最后事件 id（Last-Event-ID 头）。 */
  lastEventId?: number | null;
  onDropped?: (reason: string) => void;
  signal?: AbortSignal;
}

export interface SSEFrame {
  id: number | null;
  event: string;
  data: string;
}

/** 增量分帧器：feed 任意切块文本，产出完整帧（分块边界测试目标）。 */
export class SSEDecoder {
  private buffer = "";

  push(chunk: string): SSEFrame[] {
    // \r\n 归一为 \n（跨 chunk 的 \r + \n 也在拼接后成对）
    this.buffer = (this.buffer + chunk).replace(/\r\n/g, "\n");
    const frames: SSEFrame[] = [];
    // 帧以空行（\n\n）分界
    for (;;) {
      const idx = this.buffer.indexOf("\n\n");
      if (idx === -1) break;
      const block = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const frame = parseBlock(block);
      if (frame) frames.push(frame);
    }
    return frames;
  }

  /** 流结束时冲刷（无尾空行时的最后半帧，宽容处理）。 */
  flush(): SSEFrame[] {
    const rest = this.buffer.trim();
    this.buffer = "";
    if (!rest) return [];
    const frame = parseBlock(rest);
    return frame ? [frame] : [];
  }
}

function parseBlock(block: string): SSEFrame | null {
  let id: number | null = null;
  let event = "";
  let data: string | null = null;
  for (const rawLine of block.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("id: ")) {
      const value = line.slice(4).trim();
      id = Number.isFinite(Number(value)) ? Number(value) : null;
    } else if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data:")) {
      const value = line.startsWith("data: ") ? line.slice(6) : line.slice(5);
      data = data === null ? value : data + "\n" + value;
    }
  }
  if (data === null && !event) return null;
  return { id, event: event || "message", data: data ?? "" };
}

/** 解析一个完整 SSE 文本（测试/重放用；生产走 streamSSE 增量路径）。 */
export function decodeAllSSE(text: string): SSEFrame[] {
  const decoder = new SSEDecoder();
  return [...decoder.push(text), ...decoder.flush()];
}

/** POST SSE 流消费。onEvent 按到达顺序回调；返回 abort()。 */
export async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (frame: SSEFrame) => void,
  options: SSEOptions = {},
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (options.lastEventId != null && options.lastEventId >= 0) {
    headers["Last-Event-ID"] = String(options.lastEventId);
  }
  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new SSEHTTPError(resp.status, detail);
  }
  if (resp.headers.get("X-Engram-Events-Dropped") === "true") {
    options.onDropped?.("dropped header: events outside buffer capacity");
  }
  if (!resp.body) throw new Error("no response body");

  const decoder = new SSEDecoder();
  const reader = resp.body.getReader();
  const decoderText = new TextDecoder();

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const frame of decoder.push(decoderText.decode(value, { stream: true }))) {
        emit(frame, onEvent, options);
      }
    }
    for (const frame of decoder.flush()) emit(frame, onEvent, options);
  } finally {
    reader.releaseLock();
  }
}

function emit(frame: SSEFrame, onEvent: (f: SSEFrame) => void, options: SSEOptions) {
  if (frame.event === "error" && /resume gap exceeded/i.test(frame.data)) {
    options.onDropped?.("resume gap exceeded buffer capacity");
    return;
  }
  onEvent(frame);
}

export class SSEHTTPError extends Error {
  constructor(public status: number, public detail: string) {
    super(`SSE request failed: ${status} ${detail.slice(0, 200)}`);
  }
}

/** data JSON 解析（容错：坏 JSON 返回 null）。 */
export function parseEventData<T = unknown>(frame: SSEFrame): T | null {
  try {
    return JSON.parse(frame.data) as T;
  } catch {
    return null;
  }
}
