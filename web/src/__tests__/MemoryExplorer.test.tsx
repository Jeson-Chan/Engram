/** 记忆管理页（memory-management-ui 任务 3.2-3.6）— 集成行为测试。 */

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
    session_id: "sess-aaaabbbbcccc",
    thread_id: "thread-t1",
    user_id: "default-user",
    created_at: "2026-11-16T10:00:00",
    status: "active",
    metadata: { title: "记忆研究" },
  },
];

const traces = [
  { id: "t1", content: "用户偏好简洁回答", type: "episodic", strength: 0.8,
    decay_rate: 0.1, access_count: 3, source: "worker:thread-t1:1",
    created_at: "2026-11-18T10:00:00", forgotten: false, layer: "hot" },
  { id: "t2", content: "研究方法论沉淀", type: "semantic", strength: 0.6,
    decay_rate: 0.1, access_count: 1, source: "worker:thread-t2:1",
    created_at: "2026-11-18T11:00:00", forgotten: false, layer: "cold" },
  { id: "t3", content: "第二条 thread-t1 记忆", type: "procedural", strength: 0.4,
    decay_rate: 0.1, access_count: 0, source: "worker:thread-t1:2",
    created_at: "2026-11-18T12:00:00", forgotten: false, layer: "cold" },
];

const deleteCalls: Array<{ url: string; preview: boolean }> = [];

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

function stubApi() {
  deleteCalls.length = 0;
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method || "GET";
    if (method === "DELETE" && path.startsWith("/memory/traces")) {
      const preview = path.includes("preview=true");
      deleteCalls.push({ url: path, preview });
      if (preview) {
        const count = path.includes("thread_id=thread-t1") ? 2
          : path.includes("user_id=") ? 3 : 0;
        return jsonResponse({ grain: path.includes("thread_id=") ? "thread" : "user",
          preview: true, count, trace_ids: [] });
      }
      return jsonResponse({ grain: "trace", deleted: 1 });
    }
    if (path.startsWith("/sessions")) {
      // 会话列表 vs 会话 runs：runs 端点返回空（RunInspector 需要 run_id 字段）
      if (path.includes("/runs")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({ model: "m", provider: "p", mode: "expert",
        skills: [], mcp: [], sandbox: {} });
    }
    if (path.startsWith("/memory/traces")) return jsonResponse(traces);
    if (path.startsWith("/memory/stats")) {
      return jsonResponse({ total: 3, hot: 1, cold: 2, forgotten: 0, consolidation: 0 });
    }
    return jsonResponse([]);
  }) as unknown as typeof fetch;
}

async function openMemoryPage() {
  stubApi();
  render(<App />);
  await waitFor(() => screen.getByTestId("session-rail"));
  screen.getByTestId("nav-memory").click();
  await waitFor(() => screen.getByTestId("memory-explorer"));
}

describe("记忆管理页：分区树与列表（任务 3.3）", () => {
  it("分区树展示 user → thread 及条数，点击 thread 过滤列表", async () => {
    await openMemoryPage();
    // 树节点计数
    expect(screen.getByTestId("tree-thread-thread-t1").textContent).toContain("(2)");
    expect(screen.getByTestId("tree-thread-thread-t2").textContent).toContain("(1)");
    // 默认列表全量
    expect(screen.getByTestId("memory-item-t1")).toBeTruthy();
    expect(screen.getByTestId("memory-item-t2")).toBeTruthy();
    // 点击 thread-t1 → 仅显示该分区
    screen.getByTestId("tree-thread-thread-t1").click();
    await waitFor(() => {
      expect(screen.queryByTestId("memory-item-t2")).toBeNull();
    });
    expect(screen.getByTestId("memory-item-t1")).toBeTruthy();
    expect(screen.getByTestId("memory-item-t3")).toBeTruthy();
  });

  it("多选：勾选出现操作条并显示选中数，全选一键选中", async () => {
    await openMemoryPage();
    expect(screen.queryByTestId("memory-actionbar")).toBeNull();
    screen.getByTestId("memory-check-t1").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-actionbar").textContent).toContain("1");
    });
    screen.getByTestId("memory-check-t3").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-actionbar").textContent).toContain("2");
    });
    screen.getByTestId("memory-select-all").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-actionbar").textContent).toContain("3");
    });
  });
});

describe("记忆管理页：删除与分级确认（任务 3.4）", () => {
  it("单条删除一次点击完成", async () => {
    await openMemoryPage();
    screen.getByTestId("memory-delete-t1").click();
    await waitFor(() => {
      expect(deleteCalls.some((c) => c.url.includes("trace_id=t1") && !c.preview)).toBe(true);
    });
  });

  it("thread 清除：确认框先 preview 展示将删条数，确认后才删除", async () => {
    await openMemoryPage();
    screen.getByTestId("tree-thread-clear-thread-t1").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-confirm")).toBeTruthy();
    });
    // 预览已调用且展示条数
    expect(deleteCalls.some((c) => c.preview)).toBe(true);
    await waitFor(() => {
      expect(screen.getByTestId("confirm-count").textContent).toContain("2 条");
    });
    // 取消：无删除调用
    screen.getByText("取消").click();
    await waitFor(() => {
      expect(screen.queryByTestId("memory-confirm")).toBeNull();
    });
    expect(deleteCalls.filter((c) => !c.preview).length).toBe(0);
    // 确认：按分区删除
    screen.getByTestId("tree-thread-clear-thread-t1").click();
    await waitFor(() => screen.getByTestId("confirm-ok"));
    screen.getByTestId("confirm-ok").click();
    await waitFor(() => {
      expect(deleteCalls.some((c) =>
        !c.preview && c.url.includes("thread_id=thread-t1"))).toBe(true);
    });
  });

  it("user 清除：确认框展示全部 thread 范围", async () => {
    await openMemoryPage();
    screen.getByTestId("tree-user-clear").click();
    await waitFor(() => {
      expect(screen.getByTestId("confirm-count").textContent).toContain("3 条");
    });
  });
});

describe("记忆管理页：双向跳转（任务 3.5）", () => {
  it("来源点击切回会话模式并选中对应会话", async () => {
    await openMemoryPage();
    screen.getByTestId("memory-source-t1").click();
    await waitFor(() => {
      expect(screen.getByTestId("conversation")).toBeTruthy();
    });
    // 选中了 thread-t1 对应的会话
    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get("s")).toBe("sess-aaaabbbbcccc");
    });
  });

  it("会话模式「本会话记忆」跳入记忆页并按 thread 定位", async () => {
    stubApi();
    render(<App />);
    await waitFor(() => screen.getByTestId("session-rail"));
    screen.getByTestId("session-sess-a").click();
    await waitFor(() => screen.getByTestId("session-memories"));
    screen.getByTestId("session-memories").click();
    await waitFor(() => screen.getByTestId("memory-explorer"));
    // 已按 thread-t1 过滤：t2 不在列表
    await waitFor(() => {
      expect(screen.queryByTestId("memory-item-t2")).toBeNull();
    });
    expect(screen.getByTestId("memory-item-t1")).toBeTruthy();
  });
});

describe("记忆管理页：状态保留与空态（任务 3.2 / 3.6）", () => {
  it("筛选条件在模式切换后保留", async () => {
    await openMemoryPage();
    const input = screen.getByTestId("memory-search") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "简洁" } });
    screen.getByTestId("nav-sessions").click();
    await waitFor(() => screen.getByTestId("conversation"));
    screen.getByTestId("nav-memory").click();
    await waitFor(() => screen.getByTestId("memory-explorer"));
    const again = screen.getByTestId("memory-search") as HTMLInputElement;
    expect(again.value).toBe("简洁");
  });

  it("503 空态：提示未配置且无删除操作", async () => {
    globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method || "GET";
      if (path.startsWith("/memory/traces") && method !== "DELETE") {
        return jsonResponse({ detail: "memory not configured" }, 503);
      }
      if (path.startsWith("/memory/stats")) {
        return jsonResponse({ detail: "memory not configured" }, 503);
      }
      if (path.startsWith("/sessions")) {
      // 会话列表 vs 会话 runs：runs 端点返回空（RunInspector 需要 run_id 字段）
      if (path.includes("/runs")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
      if (path.startsWith("/status")) {
        return jsonResponse({ model: "m", provider: "p", mode: "expert",
          skills: [], mcp: [], sandbox: {} });
      }
      return jsonResponse([]);
    }) as unknown as typeof fetch;
    render(<App />);
    await waitFor(() => screen.getByTestId("session-rail"));
    screen.getByTestId("nav-memory").click();
    await waitFor(() => {
      expect(screen.getByTestId("memory-unavailable")).toBeTruthy();
    });
    expect(screen.queryByTestId("memory-tree")).toBeNull();
  });
});
