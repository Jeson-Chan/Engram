/** web-skill-override + web-config-surface 集成测试。
 *
 * 覆盖：Configs 面板（列表/启停草稿与单应用/override 设置清除/失败提示）、
 * /skill 斜杠命令（list/name/off/未知子命令、不发模型）、补全、chat 请求体
 * 携带 skill_override。
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
  { skill_id: "s-find", name: "find-skills", description: "找技能", effective_rate: 0.8,
    total_selections: 4, allowed_tools: [], enabled: true },
  { skill_id: "s-report", name: "report-gen", description: "", effective_rate: 0.5,
    total_selections: 2, allowed_tools: [], enabled: false },
];

const sseDone =
  'event: done\ndata: {"type":"done","content":"","tool_name":null,"tool_args":null,"tool_result":null,"msg_id":null}\n\n';

interface Captured { path: string; method: string; body: unknown }

function stubApi() {
  const captured: Captured[] = [];
  let enabledState: Record<string, boolean> = { "s-find": true, "s-report": false };
  const skillsNow = () => skills.map((s) => ({ ...s, enabled: enabledState[s.skill_id] }));
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
    if (method === "POST" && /\/skills\/[^/]+\/enabled$/.test(path)) {
      captured.push({ path, method, body });
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
      return jsonResponse({ reloaded: true, mcp: [] });
    }
    if (method === "POST" && path.endsWith("/sessions")) {
      return jsonResponse(sessions[0], 201);
    }
    if (path.startsWith("/sessions")) {
      if (path.includes("/runs") || path.includes("/messages")) return jsonResponse([]);
      return jsonResponse(sessions);
    }
    if (path.startsWith("/status")) {
      return jsonResponse({
        model: "m", provider: "qwen", mode: "expert", deployment: "venv",
        skills: skillsNow(), mcp: [], sandbox: {},
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

async function renderWithSession() {
  render(<App />);
  await waitFor(() => screen.getByTestId("session-sess-a"));
  fireEvent.click(screen.getByTestId("session-sess-a"));
  await waitFor(() => expect((screen.getByTestId("composer") as HTMLTextAreaElement).disabled).toBe(false));
}

async function openConfigs() {
  fireEvent.click(screen.getByTestId("configs-tab"));
  await waitFor(() => screen.getByTestId("configs-panel"));
}

describe("Configs 面板", () => {
  it("列表渲染 name/生效率/enabled；数据来自 GET /skills", async () => {
    stubApi();
    await renderWithSession();
    await openConfigs();
    const panel = screen.getByTestId("configs-panel");
    expect(panel.textContent).toContain("find-skills");
    expect(panel.textContent).toContain("找技能");
    expect(screen.getByTestId("skill-toggle-find-skills").textContent).toBe("已启用");
    expect(screen.getByTestId("skill-toggle-report-gen").textContent).toBe("已禁用");
  });

  it("启停是草稿：点击只改草稿，应用后才 POST 并刷新", async () => {
    const captured = stubApi();
    await renderWithSession();
    await openConfigs();
    fireEvent.click(screen.getByTestId("skill-toggle-find-skills"));
    // 草稿态：按钮立即翻转但不发请求
    expect(screen.getByTestId("skill-toggle-find-skills").textContent).toBe("已禁用");
    expect(captured.filter((c) => c.path.includes("/enabled"))).toHaveLength(0);
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => {
      const call = captured.find((c) => c.path.includes("/skills/s-find/enabled"));
      expect(call).toBeTruthy();
      expect((call as Captured).body).toEqual({ enabled: false });
    });
  });

  it("应用成功显示 toast 已生效!", async () => {
    stubApi();
    await renderWithSession();
    await openConfigs();
    fireEvent.click(screen.getByTestId("skill-toggle-find-skills"));
    fireEvent.click(screen.getByTestId("configs-apply"));
    const toast = await waitFor(() => screen.getByTestId("configs-toast"));
    expect(toast.textContent).toContain("已生效!");
  });

  it("override 设置（草稿）→ 应用 → chat 携带；再取消 → chat 携带空", async () => {
    const captured = stubApi();
    await renderWithSession();
    await openConfigs();
    fireEvent.click(screen.getByTestId("skill-override-find-skills"));
    expect(screen.getByTestId("skill-override-find-skills").textContent).toBe("override 中");
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => screen.getByTestId("configs-toast"));

    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "研究一下" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ skill_override: ["find-skills"] });
    });

    // 取消 override → 应用 → chat 空
    fireEvent.click(screen.getByTestId("skill-override-find-skills"));
    fireEvent.click(screen.getByTestId("configs-apply"));
    await waitFor(() => {
      const chats = captured.filter((c) => c.path.includes("/chat"));
      expect(chats).toHaveLength(1);
    });
    fireEvent.change(screen.getByTestId("composer"), { target: { value: "再来" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const chats = captured.filter((c) => c.path.includes("/chat"));
      expect((chats[1] as Captured).body).toEqual({ message: "再来", skill_override: [] });
    });
  });
});

describe("/skill 斜杠命令", () => {
  it("/skill find-skills 设置 override 且不发模型；随后 chat 请求携带 skill_override", async () => {
    const captured = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skill find-skills" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => screen.getByTestId("skill-cmd-notice"));
    expect(screen.getByTestId("skill-cmd-notice").textContent).toContain("find-skills");
    expect(captured.filter((c) => c.path.includes("/chat"))).toHaveLength(0);

    fireEvent.change(composer, { target: { value: "研究一下" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ message: "研究一下", skill_override: ["find-skills"] });
    });
  });

  it("/skill off 清除 override；后续 chat 请求携带空列表", async () => {
    const captured = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skill find-skills" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => screen.getByTestId("skill-cmd-notice"));
    fireEvent.change(composer, { target: { value: "/skill off" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => expect(screen.getByTestId("skill-cmd-notice").textContent).toContain("清除"));
    fireEvent.change(composer, { target: { value: "再来一条" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => {
      const chat = captured.find((c) => c.path.includes("/chat"));
      expect((chat as Captured).body).toMatchObject({ message: "再来一条", skill_override: [] });
    });
  });

  it("/skill list 显示激活列表（GET /skills 数据）", async () => {
    stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skill list" } });
    fireEvent.click(screen.getByTestId("send"));
    const list = await waitFor(() => screen.getByTestId("skill-cmd-list"));
    expect(list.textContent).toContain("find-skills");
    expect(list.textContent).toContain("report-gen");
  });

  it("未知子命令提示不可用且消息不发送", async () => {
    const captured = stubApi();
    await renderWithSession();
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skill evolve x" } });
    fireEvent.click(screen.getByTestId("send"));
    await waitFor(() => screen.getByTestId("skill-cmd-notice"));
    expect(screen.getByTestId("skill-cmd-notice").textContent).toContain("evolve");
    expect(captured.filter((c) => c.path.includes("/chat"))).toHaveLength(0);
  });

  it("/skill 前缀补全：空参补子命令，部分输入补 skill 名，点击回填", async () => {
    stubApi();
    await renderWithSession();
    await openConfigs(); // 打开 Configs 让 /skills 进 store（补全数据同面板）
    const composer = screen.getByTestId("composer") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "/skill " } });
    const suggest = await waitFor(() => screen.getByTestId("skill-suggest"));
    expect(suggest.textContent).toContain("list");
    expect(suggest.textContent).toContain("off");
    expect(suggest.textContent).toContain("find-skills");
    fireEvent.change(composer, { target: { value: "/skill fin" } });
    await waitFor(() => expect(screen.getByTestId("skill-suggest-find-skills")).toBeTruthy());
    fireEvent.click(screen.getByTestId("skill-suggest-find-skills"));
    expect((composer as HTMLTextAreaElement).value).toBe("/skill find-skills ");
  });
});