/** web-pixel-flavor 回归测试——wordmark/像素强度条/图标/语义类名(CRT 已删)。 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { PixelStrength } from "../components/MemoryExplorer";
import { IconSession, IconMemory } from "../components/pixel-icons";

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
  it("rail 顶部 = GitHub 仓库同款 logo GIF(与 README 展示一致)", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("wordmark"));
    const wm = screen.getByTestId("wordmark");
    const img = wm.querySelector("img");
    expect(img).toBeTruthy();
    expect(img?.getAttribute("alt")).toBe("ENGRAM");
    // GIF 资产经 vite 打包为 URL
    expect(img?.getAttribute("src")).toBeTruthy();
    // 像素锐利渲染(不模糊缩放)
    expect(img?.style.imageRendering).toBe("pixelated");
  });
});

describe("像素图标(任务 2.1)", () => {
  it("图标为 24x24 库 viewBox SVG(pixel-icon-library,crispEdges)", () => {
    const { container } = render(<IconSession />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(svg?.getAttribute("shape-rendering")).toBe("crispEdges");
    expect(svg?.getAttribute("fill")).toBe("currentColor");
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

describe("像素强度条(任务 2.4)", () => {
  it("按 strength 比例渲染 ▓ 填充 + ░ 空段(10 格)", () => {
    const { container } = render(<PixelStrength strength={0.6} />);
    const el = container.querySelector(".pixel-strength") as HTMLElement;
    expect(el.textContent).toBe("▓".repeat(6) + "░".repeat(4));
  });

  it("边界:0 = 全空,1 = 满格", () => {
    const { container: c0 } = render(<PixelStrength strength={0} />);
    expect(((c0.querySelector(".pixel-strength") as HTMLElement).textContent || "").match(/░/g)).toHaveLength(10);
    const { container: c1 } = render(<PixelStrength strength={1} />);
    expect(((c1.querySelector(".pixel-strength") as HTMLElement).textContent || "").match(/▓/g)).toHaveLength(10);
  });
});

describe("语义 CSS 契约(任务 1.1/1.2)", () => {
  it("像素图标渲染 + statusbar 主题切换按钮存在(CRT 已移除)", async () => {
    const { container } = render(<IconSession />);
    expect(container.querySelector("svg")).toBeTruthy();
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("theme-toggle"));
    expect(screen.getByTestId("theme-toggle").querySelector("svg")).toBeTruthy();
    // CRT 功能已删除:开关与 overlay 不存在
    expect(screen.queryByTestId("crt-toggle")).toBeNull();
    expect(screen.queryByTestId("crt-overlay")).toBeNull();
  });
});

describe("主题切换(web-pixel-flavor)", () => {
  it("无存储 → 跟随系统(jsdom 默认 light),点击切换并持久化", async () => {
    localStorage.removeItem("engram-theme");
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("theme-toggle"));
    // jsdom 的 matchMedia 默认不匹配 dark → 系统跟随结果为 light
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.click(screen.getByTestId("theme-toggle"));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
    });
    expect(localStorage.getItem("engram-theme")).toBe("dark");
    // 切回浅色
    fireEvent.click(screen.getByTestId("theme-toggle"));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });
    localStorage.removeItem("engram-theme");
  });

  it("有存储 → 恢复所选项(不跟随系统)", async () => {
    localStorage.setItem("engram-theme", "dark");
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("theme-toggle"));
    expect(document.documentElement.dataset.theme).toBe("dark");
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
