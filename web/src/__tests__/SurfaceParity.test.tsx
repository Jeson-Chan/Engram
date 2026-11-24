/** surface-parity web 侧：生成报告入口。 */

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";

afterEach(() => cleanup());
// App 会从 ?s= 恢复会话——用例间清 URL，避免"无会话"断言被上一用例泄漏破坏
beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

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

interface Captured { path: string; method: string }

const sseDone =
  'event: done\ndata: {"type":"done","content":"","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n';

function stubApi(opts?: { failReport?: boolean }) {
  const captured: Captured[] = [];
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    if (method === "POST" && path.includes("/chat")) {
      captured.push({ path, method });
      return new Response(sseDone, {
        status: 200, headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && path.endsWith("/report")) {
      captured.push({ path, method });
      if (opts?.failReport) return jsonResponse({ detail: "boom" }, 500);
      return jsonResponse({ artifact_path: "/tmp/report.md", final_report: "# 报告" });
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
  return captured;
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

describe("代码审查修复（web）", () => {
  it("/skill 词边界：/skills 不被当作 /skill 命令误发 override", async () => {
    const captured = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skills 请搜索" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect(chat).toBeTruthy();  // 当普通消息发出（而非本地消化成 override）
    });
    expect(screen.queryByTestId("skill-cmd-notice")).toBeNull();
  });

  it("非法旋钮输入提示（不再静默忽略）", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("configs-tab"));
    fireEvent.click(screen.getByTestId("configs-tab"));
    await waitFor(() => screen.getByTestId("configs-panel"));
    fireEvent.change(screen.getByTestId("rounds-input"), { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("rounds-apply"));
    const err = await waitFor(() => screen.getByTestId("knob-error"));
    expect(err.textContent).toContain("≥1");
  });
});

describe("生成报告（web）", () => {
  it("无选中会话禁用", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("generate-report"));
    expect((screen.getByTestId("generate-report") as HTMLButtonElement).disabled).toBe(true);
  });

  it("点击生成 → POST /sessions/{id}/report → 成功提示", async () => {
    const captured = stubApi();
    await renderWithSession();
    fireEvent.click(screen.getByTestId("generate-report"));
    await waitFor(() => {
      expect(captured.find((c) => c.path.endsWith("/report"))).toBeTruthy();
    });
    const notice = await waitFor(() => screen.getByTestId("report-notice"));
    expect(notice.textContent).toContain("报告已生成");
    expect(notice.textContent).toContain("/tmp/report.md");
  });

  it("生成失败显示错误提示", async () => {
    stubApi({ failReport: true });
    await renderWithSession();
    fireEvent.click(screen.getByTestId("generate-report"));
    const notice = await waitFor(() => screen.getByTestId("report-notice"));
    expect(notice.textContent).toContain("报告生成失败");
  });
});