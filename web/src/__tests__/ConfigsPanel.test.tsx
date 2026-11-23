/** web-config-surface 专项测试。
 *
 * 覆盖：应用失败保留草稿、模型/模式应用（POST /config）、MCP 重载、
 * 思考折叠行开关、未应用不生效。
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

const skills = [
  { skill_id: "s-find", name: "find-skills", description: "", effective_rate: 0.8,
    total_selections: 4, allowed_tools: [], enabled: true },
];

const sseWithThinking =
  'event: thinking\ndata: {"type":"thinking","content":"先想想","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n' +
  'event: done\ndata: {"type":"done","content":"","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n';

interface Captured { path: string; method: string; body: unknown }

function stubApi(opts?: { failSkillToggle?: boolean }) {
  const captured: Captured[] = [];
  let enabledState: Record<string, boolean> = { "s-find": true };
  const skillsNow = () => skills.map((s) => ({ ...s, enabled: enabledState[s.skill_id] }));
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (method === "POST" && path.includes("/chat")) {
      captured.push({ path, method, body });
      return new Response(sseWithThinking, {
        status: 200, headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && /\/skills\/[^/]+\/enabled$/.test(path)) {
      captured.push({ path, method, body });
      if (opts?.failSkillToggle) return jsonResponse({ detail: "boom" }, 500);
      const sid = decodeURIComponent(path.split("/skills/")[1].split("/enabled")[0]);
      enabledState = { ...enabledState, [sid]: body.enabled };
      return jsonResponse({ skill_id: sid, enabled: body.enabled });
    }
    if (method === "POST" && path.endsWith("/config")) {
      captured.push({ path, method, body });
      return jsonResponse({ model: "m", provider: "qwen", mode: "expert", reloaded: true });
    }
    if (method === "POST" && path.endsWith("/mcp/reload")) {
      captured.push({ path, method, body });
      return jsonResponse({ reloaded: true, mcp: [{ name: "local", transport: "stdio", health_state: "healthy" }] });
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs") || path.includes("/messages")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({
        model: "m", provider: "qwen", mode: "lightweight", deployment: "venv",
        skills: skillsNow(),
        mcp: [{ name: "local", transport: "stdio", health_state: "healthy" }],
        sandbox: {},
        models: [{ provider: "qwen", model: "qwen-plus", is_default: true }],
      });
    }
    if (path === "/skills" || path.startsWith("/skills?")) return jsonResponse(skillsNow());
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

describe("Configs 应用语义", () => {
  it("应用失败：toast 报错且草稿保留（apply 仍可用）", async () => {
    stubApi({ failSkillToggle: true });
    await openPanel();
    fireEvent.click(screen.getByTestId("skill-toggle-find-skills"));
    fireEvent.click(screen.getByTestId("configs-apply"));
    const toast = await waitFor(() => screen.getByTestId("configs-toast"));
    expect(toast.textContent).toContain("应用失败");
    // 草稿保留：按钮仍处于翻转态，应用按钮仍可用
    expect(screen.getByTestId("skill-toggle-find-skills").textContent).toBe("已禁用");
    expect((screen.getByTestId("configs-apply") as HTMLButtonElement).disabled).toBe(false);
  });

  it("模型与模式：选择后应用 → POST /config 携带 provider/expert_mode", async () => {
    const captured = stubApi();
    await openPanel();
    fireEvent.change(screen.getByTestId("cfg-model"), { target: { value: "qwen" } });
    fireEvent.change(screen.getByTestId("cfg-mode"), { target: { value: "expert" } });
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => {
      const call = captured.find((c) => c.path.endsWith("/config"));
      expect(call).toBeTruthy();
      expect((call as Captured).body).toMatchObject({ provider: "qwen", expert_mode: true });
    });
    await waitFor(() => screen.getByTestId("configs-toast"));
  });

  it("MCP 重载按钮独立生效并 toast 提示", async () => {
    const captured = stubApi();
    await openPanel();
    fireEvent.click(screen.getByTestId("cfg-mcp-reload"));
    await waitFor(() => {
      expect(captured.find((c) => c.path.endsWith("/mcp/reload"))).toBeTruthy();
    });
    const toast = await waitFor(() => screen.getByTestId("configs-toast"));
    expect(toast.textContent).toContain("MCP 已重载");
  });

  it("思考折叠行开关：应用后对话不再展示 thinking-row", async () => {
    stubApi();
    await openPanel();
    // 先发一条带 thinking 的消息
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "想想" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => screen.getByTestId("thinking-row"));

    // 关闭思考显示并应用
    fireEvent.click(screen.getByTestId("cfg-thinking"));
    expect(screen.getByTestId("cfg-thinking").textContent).toBe("已隐藏");
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => expect(screen.queryByTestId("thinking-row")).toBeNull());
  });
});