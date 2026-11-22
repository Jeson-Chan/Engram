/** 能力矩阵 tab（web-capabilities）— 只读展示 + 按需拉取 + 错误态。 */

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

const report = {
  capabilities: [
    { key: "llm", label: "对话（LLM）", state: "on", detail: "deepseek 端点可达", fix: "" },
    { key: "mcp", label: "MCP 工具", state: "broken",
      detail: "缺少 MCP 配置文件（/tmp/.engram/mcp_servers.yaml）",
      fix: "创建该文件或关闭 MCP" },
    { key: "memory_hot", label: "记忆热层（Redis）", state: "off",
      detail: "未配置 ENGRAM_REDIS_URL", fix: "" },
  ],
  connectivity: [
    { key: "llm", label: "LLM", state: "ok", detail: "deepseek 端点可达" },
    { key: "mcp", label: "MCP", state: "fail", detail: "缺少 MCP 配置文件" },
    { key: "pg", label: "Postgres", state: "skipped", detail: "未配置" },
  ],
  has_broken: true,
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

function stubApi(capabilities: unknown, status = 200) {
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    if (path.startsWith("/capabilities")) {
      return jsonResponse(capabilities, status);
    }
    if (method === "DELETE" && path.startsWith("/memory/traces")) {
      return jsonResponse({ grain: "trace", deleted: 1 });
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs")) return jsonResponse([]);
      return jsonResponse([]);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({ model: "m", provider: "p", mode: "expert",
        deployment: "venv", skills: [], mcp: [], sandbox: {} });
    }
    if (path.startsWith("/memory/traces")) return jsonResponse([]);
    if (path.startsWith("/memory/stats")) {
      return jsonResponse({ total: 0, hot: 0, cold: 0, forgotten: 0, consolidation: 0 });
    }
    return jsonResponse([]);
  }) as unknown as typeof fetch;
}

describe("CapabilityPanel（能力 tab）", () => {
  it("切换到能力 tab：按需拉取并渲染三态行（on/off/broken + 修复建议）", async () => {
    stubApi(report);
    render(<App />);
    fireEvent.click(screen.getByTestId("cap-tab"));
    await waitFor(() => screen.getByTestId("cap-llm"));
    const llm = screen.getByTestId("cap-llm");
    expect(llm.dataset.state).toBe("on");
    const mcp = screen.getByTestId("cap-mcp");
    expect(mcp.dataset.state).toBe("broken");
    expect(screen.getByText(/修复：创建该文件或关闭 MCP/)).toBeTruthy();
    const hot = screen.getByTestId("cap-memory_hot");
    expect(hot.dataset.state).toBe("off");
    // 连通性区
    expect(screen.getByTestId("conn-pg").dataset.state).toBe("skipped");
    // broken 汇总标记
    expect(screen.getByText("有 broken 项")).toBeTruthy();
    // 部署徽章（statusbar，venv 后端）
    expect(screen.getByTestId("deployment-badge").textContent).toBe("venv");
    // 帮助折叠：默认收起，点击展开后注脚可见
    expect(screen.queryByTestId("config-tui-only-note")).toBeNull();
    fireEvent.click(screen.getByTestId("capability-help-toggle"));
    expect(screen.getByTestId("config-tui-only-note").textContent).toContain("TUI");
    // 再点收起
    fireEvent.click(screen.getByTestId("capability-help-toggle"));
    expect(screen.queryByTestId("config-tui-only-note")).toBeNull();
  });

  it("端点失败：显式错误态而非空白", async () => {
    stubApi({ detail: "probe failed: boom" }, 503);
    render(<App />);
    fireEvent.click(screen.getByTestId("cap-tab"));
    await waitFor(() => screen.getByTestId("capabilities-error"));
    expect(screen.getByTestId("capabilities-error").textContent).toContain("能力数据不可用");
  });
});
