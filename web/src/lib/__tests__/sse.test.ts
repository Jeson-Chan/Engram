/**
 * SSE 解析器测试 — 契约来源：docs/event-semantics.md（任务 1.3 前端引用）。
 *
 * 后端契约测试（engram/backend/tests/v1/unit/gateway/test_event_semantics.py）
 * 解析同一份文档——两侧共用同一份事实。
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  SSEDecoder,
  decodeAllSSE,
  parseEventData,
  type SSEFrame,
} from "../sse";
import type { StreamEvent } from "../types";

// 文档路径：仓库根/docs/event-semantics.md（vitest 从 web/ 起——cwd 相对；
// jsdom 环境下 import.meta.url 非 file scheme，不能用 new URL）
const docText = readFileSync(
  path.resolve(process.cwd(), "..", "docs", "event-semantics.md"),
  "utf-8",
);

/** 提取文档全部 ```sse 示例块（与后端测试同构）。
 * Windows 检出为 CRLF：```​sse 后允许 \r\n（与 LF 检出行为一致）。 */
function extractDocBlocks(): string[] {
  const blocks = [...docText.matchAll(/```sse\r?\n(.*?)```/gs)]
    .map((m) => m[1].replace(/\r\n/g, "\n"));
  expect(blocks.length).toBeGreaterThan(0);
  return blocks;
}

function parseEvents(text: string): Array<{ frame: SSEFrame; data: StreamEvent | null }> {
  return decodeAllSSE(text).map((frame) => ({
    frame,
    data: parseEventData<StreamEvent>(frame),
  }));
}

describe("文档契约（docs/event-semantics.md 示例块）", () => {
  it("每块解析出非空帧序列，id 从 1 连续递增", () => {
    for (const block of extractDocBlocks()) {
      const frames = decodeAllSSE(block);
      expect(frames.length).toBeGreaterThan(0);
      const ids = frames.map((f) => f.id);
      expect(ids).toEqual(ids.map((_, i) => i + 1));
    }
  });

  it("event 行与 data.type 一致；公共字段齐全", () => {
    for (const block of extractDocBlocks()) {
      for (const { frame, data } of parseEvents(block)) {
        expect(data).not.toBeNull();
        if (data) {
          expect(data.type).toBe(frame.event);
          for (const field of ["type", "content", "tool_name", "tool_args", "tool_result", "msg_id"]) {
            expect(data).toHaveProperty(field);
          }
        }
      }
    }
  });

  it("每个示例流以 done 收尾（客户端终态判定契约）", () => {
    for (const block of extractDocBlocks()) {
      const frames = decodeAllSSE(block);
      expect(frames[frames.length - 1].event).toBe("done");
    }
  });

  it("tool_start/tool_end 关键字段非空；budget_update 带 budget 快照", () => {
    let sawBudget = false;
    for (const block of extractDocBlocks()) {
      for (const { data } of parseEvents(block)) {
        if (!data) continue;
        if (data.type === "tool_start") {
          expect(data.tool_name).toBeTruthy();
        } else if (data.type === "tool_end") {
          expect(data.tool_name).toBeTruthy();
          expect(data.tool_result).toBeTruthy();
        } else if (data.type === "budget_update") {
          sawBudget = true;
          expect(data.budget).toMatchObject({
            total: expect.any(Number),
            fraction: expect.any(Number),
            window: expect.any(String),
          });
        }
      }
    }
    expect(sawBudget).toBe(true);
  });
});

describe("分块边界（任意切块也能正确分帧）", () => {
  const block = extractDocBlocks()[0];

  it("逐字节切块解析 == 整体解析", () => {
    const whole = decodeAllSSE(block);
    const decoder = new SSEDecoder();
    let chunked: SSEFrame[] = [];
    for (const ch of block) {
      chunked = [...chunked, ...decoder.push(ch)];
    }
    chunked = [...chunked, ...decoder.flush()];
    expect(chunked).toEqual(whole);
  });

  it("极端边界：每帧切成 3 段", () => {
    const whole = decodeAllSSE(block);
    const decoder = new SSEDecoder();
    let out: SSEFrame[] = [];
    const size = Math.ceil(block.length / 3);
    for (let i = 0; i < block.length; i += size) {
      out = [...out, ...decoder.push(block.slice(i, i + size))];
    }
    out = [...out, ...decoder.flush()];
    expect(out).toEqual(whole);
  });

  it("\\r\\n 换行同样可解析", () => {
    const crlf = block.replace(/\n/g, "\r\n");
    expect(decodeAllSSE(crlf)).toEqual(decodeAllSSE(block));
  });
});

describe("断线续传语义", () => {
  it("gap 错误帧（resume gap exceeded）可被识别为 dropped", () => {
    const gapFrame = `event: error\ndata: {"type":"error","content":"resume gap exceeded buffer capacity","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n`;
    const frames = decodeAllSSE(gapFrame);
    expect(frames).toHaveLength(1);
    // streamSSE 的 onDropped 判定逻辑即此正则
    expect(/resume gap exceeded/i.test(frames[0].data)).toBe(true);
  });

  it("多 data: 行拼接（SSE 规范）", () => {
    const twoLines = `event: answer\ndata: {"type":"answer",\ndata: "content":"x"}\n\n`;
    const frames = decodeAllSSE(twoLines);
    expect(frames).toHaveLength(1);
    expect(frames[0].data).toBe('{"type":"answer",\n"content":"x"}');
  });
});

describe("streamSSE（fetch 层）", () => {
  it("携带 Last-Event-ID 请求头并以错误事件明示 dropped", async () => {
    const seenHeaders: Record<string, string> = {};
    globalThis.fetch = (async (_url: unknown, init?: RequestInit) => {
      for (const [k, v] of Object.entries(init?.headers || {})) {
        seenHeaders[k.toLowerCase()] = String(v);
      }
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              `event: error\ndata: {"type":"error","content":"resume gap exceeded buffer capacity","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n`,
            ),
          );
          controller.close();
        },
      });
      return new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }) as unknown as typeof fetch;

    const events: SSEFrame[] = [];
    let dropped: string | null = null;
    const { streamSSE } = await import("../sse");
    await streamSSE("/sessions/x/chat", { message: "q" }, (f) => events.push(f), {
      lastEventId: 42,
      onDropped: (reason) => {
        dropped = reason;
      },
    });
    expect(seenHeaders["last-event-id"]).toBe("42");
    expect(dropped).toBeTruthy(); // gap 事件不静默拼接：明示 dropped
    expect(events).toHaveLength(0); // gap 帧不外发
  });
});
