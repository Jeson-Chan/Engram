/** runtime-knobs 集成测试（web-config-surface 草稿语义）。
 *
 * 覆盖：运行参数区默认 auto/来源标记、设置→应用→请求体携带、think 显示开关、
 * provider 支持性标注。
 */

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

function stubApi(provider = "qwen") {
  const captured: Captured[] = [];
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (method === "POST" && path.includes("/chat")) {
      captured.push({ path, method, body });
      return new Response(sseDone, {
        status: 200, headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && path.endsWith("/config")) {
      captured.push({ path, method, body });
      return jsonResponse({ model: "m", provider, mode: "expert", reloaded: true });
    }
    if (method === "POST" && path.endsWith("/mcp/reload")) {
      captured.push({ path, method, body });
      return jsonResponse({ reloaded: true, mcp: [] });
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs") || path.includes("/messages")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({
        model: "m", provider, mode: "expert", deployment: "venv",
        skills: [], mcp: [], sandbox: {},
        models: [{ provider, model: "x", is_default: true }],
      });
    }
    if (path === "/skills" || path.startsWith("/skills?")) return jsonResponse([]);
    if (path.startsWith("/capabilities")) return jsonResponse({ deployment: "venv", capabilities: [], connectivity: [] });
    if (path.startsWith("/memory")) return jsonResponse([]);
    return jsonResponse([]);
  }) as unknown as typeof fetch;
  return captured;
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

async function openPanel() {
  render(<App />);
  await waitFor(() => screen.getByTestId("session-sess-a"));
  fireEvent.click(screen.getByTestId("session-sess-a"));
  await waitFor(() => expect((screen.getByTestId("composer") as HTMLTextAreaElement).disabled).toBe(false));
  fireEvent.click(screen.getByTestId("configs-tab"));
  await waitFor(() => screen.getByTestId("configs-panel"));
}

async function sendChat(text: string) {
  const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
  fireEvent.change(composer, { target: { value: text } });
  fireEvent.click(screen.getByTestId("send"));
  await waitFor(() => expect(screen.getByTestId("composer")).toBeTruthy());
}

describe("运行参数区（草稿 + 应用）", () => {
  it("默认全部 auto；来源标记正确", async () => {
    stubApi();
    await openPanel();
    expect(screen.getByTestId("rounds-source").textContent).toContain("auto");
    expect(screen.getByTestId("effort-source").textContent).toContain("auto");
    expect(screen.getByTestId("window-source").textContent).toContain("auto");
  });

  it("轮数：框内直接改（草稿）→ 应用 → manual + 请求体携带；清除应用后恢复 auto", async () => {
    const captured = stubApi();
    await openPanel();
    fireEvent.change(screen.getByTestId("rounds-input"), { target: { value: "10" } });
    // 草稿态：尚未应用到运行时
    expect(screen.getByTestId("rounds-source").textContent).toContain("auto");
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.getByTestId("rounds-source").textContent).toContain("manual"));

    await sendChat("第一条");
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ message: "第一条", max_loop_steps: 10 });
    });

    fireEvent.click(screen.getByTestId("rounds-clear"));
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.getByTestId("rounds-source").textContent).toContain("auto"));
    await sendChat("第二条");
    await waitFor(() => {
      const chats = captured.filter((c) => c.path.includes("/chat"));
      const body = (chats[1] as Captured).body as Record<string, unknown>;
      expect(body.max_loop_steps).toBeUndefined();
    });
  });

  it("思考强度：选 medium 应用后请求体携带；off 不携带", async () => {
    const captured = stubApi();
    await openPanel();
    fireEvent.change(screen.getByTestId("effort-select"), { target: { value: "medium" } });
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.getByTestId("effort-source").textContent).toContain("medium"));
    await sendChat("想一想");
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ reasoning_effort: "medium" });
    });
    fireEvent.change(screen.getByTestId("effort-select"), { target: { value: "off" } });
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.getByTestId("effort-source").textContent).toContain("auto"));
    await sendChat("别想了");
    await waitFor(() => {
      const chats = captured.filter((c) => c.path.includes("/chat"));
      const body = (chats[1] as Captured).body as Record<string, unknown>;
      expect(body.reasoning_effort).toBeUndefined();
    });
  });

  it("窗口：框内直接改应用后请求体携带 context_window", async () => {
    const captured = stubApi();
    await openPanel();
    fireEvent.change(screen.getByTestId("window-input"), { target: { value: "32000" } });
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.getByTestId("window-source").textContent).toContain("32000"));
    await sendChat("压缩我");
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ context_window: 32000 });
    });
  });

  it("provider 支持性：deepseek 标注不支持，qwen 不标注", async () => {
    stubApi("deepseek");
    await openPanel();
    expect(screen.getByTestId("effort-source").textContent).toContain("不支持");
    cleanup();
    stubApi("qwen");
    await openPanel();
    expect(screen.getByTestId("effort-source").textContent).not.toContain("不支持");
  });
});