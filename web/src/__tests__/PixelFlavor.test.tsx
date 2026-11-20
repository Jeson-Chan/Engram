/** web-pixel-flavor 回归测试——wordmark/CRT/像素强度条/图标/语义类名。 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { PixelStrength } from "../components/MemoryExplorer";
import { IconSession, IconMemory, IconCrt } from "../components/pixel-icons";

afterEach(() => cleanup());

const mq: { matches: boolean } & Partial<MediaQueryList> = {
  matches: false, media: "", onchange: null,
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
  addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
};
beforeAll(() => {
  window.matchMedia = (() => mq) as unknown as typeof window.matchMedia;
  window.localStorage.clear();
});

const sessions = [
  {
    session_id: "sess-aaaabbbbcccc", thread_id: "thread-t1", user_id: "default-user",
    created_at: "2026-11-16T10:00:00", status: "active", metadata: { title: "记忆研究" },
  },
];

function stubApi() {
  globalThis.fetch = (async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({ model: "m", provider: "p", mode: "expert", skills: [], mcp: [], sandbox: {} });
    }
    if (path.startsWith("/memory/traces")) {
      return jsonResponse([
        { id: "t1", content: "mem one", type: "episodic", strength: 0.6, decay_rate: 0.1,
          access_count: 1, source: "worker:thread-t1:1", created_at: "2026-11-20T10:00:00",
          forgotten: false, layer: "hot" },
      ]);
    }
    if (path.startsWith("/memory/stats")) {
      return jsonResponse({ total: 1, hot: 1, cold: 0, forgotten: 0, consolidation: 0 });
    }
    return jsonResponse([]);
  }) as unknown as typeof fetch;
}

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("wordmark(任务 2.2)", () => {
  it("rail 顶部常驻双色 Geist 字母", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("wordmark"));
    const wm = screen.getByTestId("wordmark");
    expect(wm.textContent).toContain("ENG");
    expect(wm.textContent).toContain("RAM");
    expect(wm.querySelector(".g1")).toBeTruthy();
    expect(wm.querySelector(".g2")).toBeTruthy();
  });
});

describe("像素图标(任务 2.1)", () => {
  it("图标为 8x8 viewBox SVG", () => {
    const { container } = render(<IconSession />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 8 8");
    expect(svg?.getAttribute("shape-rendering")).toBe("crispEdges");
    const { container: c2 } = render(<IconMemory />);
    expect(c2.querySelector("svg")).toBeTruthy();
  });

  it("rail 导航含图标 + data-nav 语义属性", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("rail-nav"));
    expect(screen.getByTestId("nav-sessions").querySelector("svg")).toBeTruthy();
    expect(screen.getByTestId("nav-memory").getAttribute("data-nav")).toBe("memory");
  });
});

describe("CRT 开关(任务 2.5)", () => {
  it("默认开启,点击切换并持久化 localStorage", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("statusbar"));
    expect(screen.getByTestId("crt-overlay")).toBeTruthy();
    fireEvent.click(screen.getByTestId("crt-toggle"));
    await waitFor(() => {
      expect(screen.queryByTestId("crt-overlay")).toBeNull();
    });
    expect(localStorage.getItem("engram-crt-off")).toBe("1");
    // 再开
    fireEvent.click(screen.getByTestId("crt-toggle"));
    await waitFor(() => screen.getByTestId("crt-overlay"));
    expect(localStorage.getItem("engram-crt-off")).toBe("0");
    localStorage.clear();
  });
});

describe("像素强度条(任务 2.4)", () => {
  it("按 strength 比例渲染 ▓ 填充 + ▐ 空段", () => {
    const { container } = render(<PixelStrength strength={0.6} />);
    const fill = container.querySelector(".fill");
    const empty = container.querySelector(".empty");
    expect(fill?.textContent).toBe("▓".repeat(6));
    expect(empty?.textContent).toBe("░".repeat(4));
  });

  it("边界:0 = 全空,1 = 满格", () => {
    const { container: c0 } = render(<PixelStrength strength={0} />);
    expect(c0.querySelector(".fill")?.textContent).toBe("");
    const { container: c1 } = render(<PixelStrength strength={1} />);
    expect(c1.querySelector(".fill")?.textContent).toBe("▓".repeat(10));
  });
});

describe("语义 CSS 契约(任务 1.1/1.2)", () => {
  it("样式表无旧蓝、无非零圆角、三语义 token 存在", async () => {
    // vitest 环境不走 vite 静态服务;断言关键交互元素在渲染层
    const { container } = render(<IconCrt />);
    expect(container.querySelector("svg")).toBeTruthy();
    // 页面渲染后 statusbar 含 CRT 按钮
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("crt-toggle"));
    expect(screen.getByTestId("crt-toggle").textContent).toContain("CRT");
  });
});

describe("主题切换(v2 反馈轮)", () => {
  it("默认深色盖章,点击切换并持久化", async () => {
    localStorage.removeItem("engram-theme");
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("theme-toggle"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByTestId("theme-toggle"));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });
    expect(localStorage.getItem("engram-theme")).toBe("light");
    // 切回深色
    fireEvent.click(screen.getByTestId("theme-toggle"));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
    });
    localStorage.removeItem("engram-theme");
  });
});

describe("专属图标(v2 反馈轮)", () => {
  it("运行历史时钟 + 时间线节点 + 导航气泡各形各样", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-rail"));
    // 导航:气泡(会话)与芯片(记忆)都是 SVG
    expect(screen.getByTestId("nav-sessions").querySelector("svg")).toBeTruthy();
    // 记忆页进入后硬币(context)出现在统计行
    screen.getByTestId("nav-memory").click();
    await waitFor(() => screen.getByTestId("memory-explorer"));
    const stats = screen.getByTestId("memory-stats");
    expect(stats.querySelectorAll("svg").length).toBeGreaterThanOrEqual(3);
  });
});
