/** web-workbench-interactions 集成测试。
 *
 * 覆盖：工具池 chip 各自弹层（数据来自 /status）、记忆按钮禁用态、
 * statusbar 瘦身、会话 id 展示、行内重命名（确认/取消/空值）。
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

const status = {
  model: "m", provider: "p", mode: "expert", deployment: "venv",
  skills: [
    { skill_id: "find-skills", name: "find-skills" },
    { skill_id: "report-gen", name: "report-gen" },
    { skill_id: "web-helper", name: "web-helper" },
  ],
  mcp: [
    { name: "local", transport: "stdio", tool_count: 4, health_state: "healthy" },
    { name: "search", transport: "sse", tool_count: 2, health_state: "degraded" },
  ],
  sandbox: {},
};

const patchCalls: Array<{ url: string; body: unknown }> = [];

function stubApi(opts?: { emptyPools?: boolean; patchFail?: boolean }) {
  patchCalls.length = 0;
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    if (method === "PATCH" && path.startsWith("/sessions/")) {
      patchCalls.push({ url: path, body: JSON.parse(String(init?.body)) });
      if (opts?.patchFail) return jsonResponse({ detail: "boom" }, 500);
      return jsonResponse({
        ...sessions[0],
        metadata: { title: JSON.parse(String(init?.body)).title },
      });
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      if (opts?.emptyPools) {
        return jsonResponse({ ...status, skills: [], mcp: [] });
      }
      return jsonResponse(status);
    }
    if (path.startsWith("/capabilities")) {
      return jsonResponse({
        deployment: "venv",
        capabilities: [{ key: "llm", label: "LLM", state: "on", detail: "ok", fix: "" }],
        connectivity: [{ key: "llm", label: "LLM", state: "ok", detail: "ok" }],
      });
    }
    if (path.startsWith("/memory/traces")) return jsonResponse([]);
    if (path.startsWith("/memory/stats")) {
      return jsonResponse({ total: 0, hot: 0, cold: 0, forgotten: 0, consolidation: 0 });
    }
    return jsonResponse([]);
  }) as unknown as typeof fetch;
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

describe("输入区无工具池 chips（web-config-surface）", () => {
  it("composer 旁无 skills/MCP chip（改由右栏 Configs 展示）", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("statusbar"));
    expect(screen.queryByTestId("pool-chip-row")).toBeNull();
    expect(screen.queryByTestId("pool-chip-skills")).toBeNull();
    expect(screen.queryByTestId("pool-chip-mcp")).toBeNull();
  });
});

describe("statusbar 瘦身 + 记忆按钮禁用态", () => {
  it("无 skills/MCP 计数徽章；无会话时记忆按钮 disabled", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("statusbar"));
    // 计数徽章不再出现
    expect(screen.queryByText(/skills$/)).toBeNull();
    expect(screen.queryByText(/MCP$/)).toBeNull();
    // 无当前会话 → 按钮常驻但禁用
    const btn = screen.getByTestId("session-memories") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe("本会话记忆");
  });

  it("选中会话后记忆按钮可点", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-sess-a"));
    fireEvent.click(screen.getByTestId("session-sess-a"));
    await waitFor(() => {
      const btn = screen.getByTestId("session-memories") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
  });
});

describe("会话 id 展示 + 行内重命名", () => {
  it("会话项显示 mono 短 id", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-sess-a"));
    expect(screen.getByTestId("session-id").textContent).toBe("sess-aaaabbb");
  });

  it("点击铅笔进入行内编辑，Enter 确认发 PATCH", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-sess-a"));
    fireEvent.click(screen.getByTestId("rename-sess-a"));
    const input = await waitFor(() => screen.getByTestId("rename-input"));
    expect((input as HTMLInputElement).value).toBe("记忆研究");
    fireEvent.change(input, { target: { value: "新标题" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(patchCalls).toHaveLength(1));
    expect(patchCalls[0].body).toEqual({ title: "新标题" });
    // 编辑态退出，title 更新（乐观）
    expect(screen.queryByTestId("rename-input")).toBeNull();
    expect(screen.getByTestId("session-title").textContent).toBe("新标题");
  });

  it("Esc 取消：不发请求，title 恢复", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-sess-a"));
    fireEvent.click(screen.getByTestId("rename-sess-a"));
    const input = await waitFor(() => screen.getByTestId("rename-input"));
    fireEvent.change(input, { target: { value: "改一半" } });
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("rename-input")).toBeNull());
    expect(patchCalls).toHaveLength(0);
    expect(screen.getByTestId("session-title").textContent).toBe("记忆研究");
  });

  it("清空后确认 = 取消（不发请求）", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-sess-a"));
    fireEvent.click(screen.getByTestId("rename-sess-a"));
    const input = await waitFor(() => screen.getByTestId("rename-input"));
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.queryByTestId("rename-input")).toBeNull());
    expect(patchCalls).toHaveLength(0);
    expect(screen.getByTestId("session-title").textContent).toBe("记忆研究");
  });
});
