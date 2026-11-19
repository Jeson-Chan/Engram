/** 三栏壳 + 响应式收起 + 选中会话 URL 状态（任务 5.3）。 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "../App";

// vitest 关闭 globals 模式时 RTL 不会自动注册 cleanup——手动挂
afterEach(() => cleanup());

const narrowMq: { matches: boolean } & Partial<MediaQueryList> = {
  matches: false, media: "", onchange: null,
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
  addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
};
const wideMq: { matches: boolean } & Partial<MediaQueryList> = {
  matches: false, media: "", onchange: null,
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
  addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
};
const mqMap: Record<string, { matches: boolean } & Partial<MediaQueryList>> = {
  "(max-width: 900px)": wideMq,
};
// localStorage / location
beforeAll(() => {
  window.matchMedia = ((query: string) =>
    mqMap[query] ?? narrowMq) as unknown as typeof window.matchMedia;
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
    if (path.startsWith("/memory/traces")) {
      return jsonResponse([]);
    }
    if (path.startsWith("/memory/stats")) {
      return jsonResponse({ total: 0, hot: 0, cold: 0, forgotten: 0, consolidation: 0 });
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
      expect(screen.getByTestId("session-sess-a")).toBeTruthy();
    });
    screen.getByTestId("session-sess-a").click();
    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get("s")).toBe("sess-aaaabbbbcccc");
    });
  });

  it("rail 记忆导航切换主区为记忆管理页", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("run-inspector")).toBeTruthy();
    });
    screen.getByTestId("nav-memory").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-explorer")).toBeTruthy();
    });
    // 主区整体切换：对话区与 inspector 暂离
    expect(screen.queryByTestId("conversation")).toBeNull();
    expect(screen.queryByTestId("inspector")).toBeNull();
    // 切回会话模式
    screen.getByTestId("nav-sessions").click();
    await waitFor(() => {
      expect(screen.getByTestId("conversation")).toBeTruthy();
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
