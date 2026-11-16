/** 三栏壳 + 响应式收起 + 选中会话 URL 状态（任务 5.3）。 */

import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";

const narrowMq = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
const wideMq = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
const mqMap: Record<string, MediaQueryList> = {
  "(max-width: 900px)": wideMq,
};
// localStorage / location
beforeAll(() => {
  window.matchMedia = (query: string) => mqMap[query] ?? narrowMq;
});

const sessions = [
  {
    session_id: "sess-aaaabbbbcccc",
    thread_id: "thread-t1",
    user_id: "default-user",
    created_at: "2026-11-16T10:00:00",
    status: "active",
    metadata: { title: "记忆研究" },
  },
  {
    session_id: "sess-ddddeeeeffff",
    thread_id: "thread-t2",
    user_id: "default-user",
    created_at: "2026-11-16T11:00:00",
    status: "active",
    metadata: {},
  },
];

function stubApi() {
  globalThis.fetch = (async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.startsWith("/sessions?") || path === "/sessions") {
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({
        model: "deepseek-v4.1", provider: "openai", mode: "expert",
        skills: [{ skill_id: "s" }], mcp: [], sandbox: {},
      });
    }
    return jsonResponse([]);
  }) as unknown as typeof fetch;
}

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("App 三栏壳（宽视口）", () => {
  it("显示会话栏 / 对话区 / Run Inspector 三个区域", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("session-rail")).toBeTruthy();
    });
    expect(screen.getByTestId("conversation")).toBeTruthy();
    expect(screen.getByTestId("inspector")).toBeTruthy();
    expect(screen.getByTestId("run-inspector")).toBeTruthy();
    // 状态栏展示模型
    expect(screen.getByTestId("model-name").textContent).toContain("deepseek");
    // 会话列表渲染标题
    expect(screen.getAllByText("记忆研究").length).toBeGreaterThan(0);
  });

  it("点击会话选中并写入 URL ?s=", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("session-aaaabb")).toBeTruthy();
    });
    screen.getByTestId("session-aaaabb").click();
    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get("s")).toBe("sess-aaaabbbbcccc");
    });
  });

  it("记忆面板可切换（Inspector tab）", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("run-inspector")).toBeTruthy();
    });
    const memoryTab = screen.getByText("Memory");
    memoryTab.click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-explorer")).toBeTruthy();
    });
  });
});

describe("App 窄视口（收起 Inspector / 会话栏为抽屉）", () => {
  it("默认只渲染对话区，抽屉按钮可打开会话栏", async () => {
    mqMap["(max-width: 900px)"] = narrowMq;
    narrowMq.matches = true;
    stubApi();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("conversation")).toBeTruthy();
    });
    // 收起：rail / inspector 不可见（display:none 断言为样式）
    expect(screen.queryByTestId("session-rail")).toBeNull();
    expect(screen.queryByTestId("inspector")).toBeNull();
    // 打开会话抽屉
    screen.getByText("会话").click();
    await waitFor(() => {
      expect(screen.getByTestId("session-rail")).toBeTruthy();
    });
    // 输入框保持可用（不受遮挡影响的功能断言）
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    expect(composer.tagName).toBe("TEXTAREA");
    narrowMq.matches = false;
    mqMap["(max-width: 900px)"] = wideMq;
  });
});
