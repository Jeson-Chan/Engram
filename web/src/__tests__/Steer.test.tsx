/** real-steer web 侧：流中插话 / 已注入反馈 / 空闲正常发送 / 失败保留草稿。 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";

afterEach(() => cleanup());

const mq: { matches: boolean } & Partial<MediaQueryList> = {
  matches: false, media: "", onchange: null,
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
  addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
};
beforeAll(() => {
  window.matchMedia = (() => mq) as unknown as typeof window.matchMedia;
});

const sessions = [
  {
    session_id: "sess-aaaabbbbcccc", thread_id: "thread-t1", user_id: "default-user",
    created_at: "2026-11-16T10:00:00", status: "active", metadata: { title: "记忆研究" },
  },
];

const sseDone =
  'event: done\ndata: {"type":"done","content":"","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n';

interface Captured { path: string; method: string; body: unknown }

function stubApi(opts?: { failSteer?: boolean }) {
  const captured: Captured[] = [];
  let streamController: ReadableStreamDefaultController | null = null;
  const encoder = new TextEncoder();
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (method === "POST" && path.includes("/chat")) {
      captured.push({ path, method, body });
      // 永不关闭的流：维持 streaming 态供插话测试；测试经 controller 推帧
      const stream = new ReadableStream({
        start(c) {
          streamController = c;
          c.enqueue(encoder.encode(sseDone.replace("done", "answer").replace(
            '"type":"done"', '"type":"answer","content":"working"',
          )));
        },
      });
      return new Response(stream, {
        status: 200, headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && path.endsWith("/steer")) {
      captured.push({ path, method, body });
      if (opts?.failSteer) return jsonResponse({ detail: "no active run" }, 409);
      return jsonResponse({ accepted: true, thread_id: "thread-t1" });
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs") || path.includes("/messages")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({
        model: "m", provider: "qwen", mode: "lightweight", deployment: "venv",
        skills: [], mcp: [], sandbox: {}, models: [],
      });
    }
    if (path === "/skills" || path.startsWith("/skills?")) return jsonResponse([]);
    if (path.startsWith("/capabilities")) return jsonResponse({ deployment: "venv", capabilities: [], connectivity: [] });
    if (path.startsWith("/memory")) return jsonResponse([]);
    return jsonResponse([]);
  }) as unknown as typeof fetch;
  return { captured, getController: () => streamController, encoder };
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

async function renderWithSession() {
  render(<App />);
  await waitFor(() => screen.getByTestId("session-sess-a"));
  fireEvent.click(screen.getByTestId("session-sess-a"));
  await waitFor(() => expect((screen.getByTestId("composer") as HTMLTextAreaElement).disabled).toBe(false));
}

describe("运行中插话（real-steer web）", () => {
  it("流式中回车 → POST /steer + 已插话提示", async () => {
    const { captured } = stubApi();
    await renderWithSession();
    // 发起一条永不结束的流 → streaming=true
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "长任务" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => expect(captured.find((c) => c.path.includes("/chat"))).toBeTruthy());

    // 流式中输入 → 按钮变"插话" → 回车走 steer
    fireEvent.change(composer, { target: { value: "补充：只看 2024" } });
    expect(screen.getByTestId("send").textContent).toBe("插话");
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const steer = captured.find((c) => c.path.endsWith("/steer"));
      expect(steer).toBeTruthy();
      expect((steer as Captured).body).toMatchObject({ message: "补充：只看 2024" });
    });
    const notice = await waitFor(() => screen.getByTestId("steer-notice"));
    expect(notice.textContent).toContain("已插话");
    // 成功后草稿清空
    expect((composer as HTMLTextAreaElement).value).toBe("");
  });

  it("steer_injected 事件 → 已注入提示", async () => {
    const { getController, encoder } = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "长任务" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => expect(getController()).toBeTruthy());

    const frame =
      'event: steer_injected\ndata: {"type":"steer_injected","content":"补充：只看 2024","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n';
    getController()!.enqueue(encoder.encode(frame));
    const notice = await waitFor(() => screen.getByTestId("steer-notice"));
    expect(notice.textContent).toContain("已注入");
  });

  it("空闲时回车走正常发送（不入队）", async () => {
    const { captured } = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "普通消息" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      expect(captured.find((c) => c.path.includes("/chat"))).toBeTruthy();
    });
    expect(captured.find((c) => c.path.endsWith("/steer"))).toBeUndefined();
  });

  it("插话失败：错误提示且草稿保留", async () => {
    const { captured } = stubApi({ failSteer: true });
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "长任务" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => expect(captured.find((c) => c.path.includes("/chat"))).toBeTruthy());

    fireEvent.change(composer, { target: { value: "迟到的补充" } });
    fireEvent.click(screen.getByTestId("send"));
    const notice = await waitFor(() => screen.getByTestId("steer-notice"));
    expect(notice.textContent).toContain("插话失败");
    expect((composer as HTMLTextAreaElement).value).toBe("迟到的补充"); // 草稿保留
  });
});