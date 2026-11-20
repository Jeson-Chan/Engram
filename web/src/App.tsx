import { useEffect, useRef, useState } from "react";
import { AppProvider, useApp } from "./store";
import { SessionRail } from "./components/SessionRail";
import { Conversation } from "./components/Conversation";
import { RunInspector } from "./components/RunInspector";
import { MemoryExplorer } from "./components/MemoryExplorer";
import { IconCrt, IconRun, IconSun, IconMoon } from "./components/pixel-icons";
import "./styles.css";

/** 深/浅主题切换:盖章 documentElement.dataset.theme + localStorage 持久化;无记录跟随系统。 */
function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => {
    // 无存储记录 → 跟随系统(spec:首次访问跟随 prefers-color-scheme)
    try {
      const stored = localStorage.getItem("engram-theme");
      if (stored === "light" || stored === "dark") return stored;
    } catch { /* 隐私模式 */ }
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("engram-theme", theme);
    } catch { /* 忽略 */ }
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return [theme, toggle];
}

/** CRT overlay 偏好(localStorage 持久化;reduced-motion/低核自动关)。 */
function useCrtEnabled(): [boolean, (on: boolean) => void, boolean] {
  const [forcedOff] = useState(() => {
    if (typeof window === "undefined") return false;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lowEnd = (navigator.hardwareConcurrency ?? 8) < 4;
    return reduced || lowEnd;
  });
  const [off, setOff] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      return localStorage.getItem("engram-crt-off") !== "1" && !forcedOff;
    } catch {
      return !forcedOff;
    }
  });
  const set = (on: boolean) => {
    setOff(on);
    try {
      localStorage.setItem("engram-crt-off", on ? "0" : "1");
    } catch { /* 私有模式等:偏好不持久化,可接受 */ }
  };
  return [off, set, forcedOff];
}

/** 响应式三栏壳：窄屏（<900px）收起 Inspector 与会话栏（可开抽屉）。 */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function Shell() {
  const { state, actions } = useApp();
  const narrow = useNarrow();
  const [drawer, setDrawer] = useState<"sessions" | "run" | "memory" | null>(null);
  const [crtOn, setCrtOn, crtForcedOff] = useCrtEnabled();
  const [theme, toggleTheme] = useTheme();

  // 刷新恢复（任务 5.7）：mount 时刻缓存 URL 里的 ?s=——URL-clear effect
  // 在 currentSessionId 仍为 null 的首帧就会删参数，晚读就丢了
  const initialSid = useRef(
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("s")
      : null,
  );

  useEffect(() => {
    actions.refreshSessions();
    actions.refreshStatus();
  }, [actions]);

  useEffect(() => {
    const sid = initialSid.current;
    if (sid && state.sessions.some((s) => s.session_id === sid)) {
      actions.selectSession(sid);
      initialSid.current = null; // 恢复一次即失效（后续切换由选中状态驱动）
    }
  }, [state.sessions]); // eslint-disable-line react-hooks/exhaustive-deps

  // URL 同步（review medium：StrictMode 双调 mount 使"首帧跳过"守卫失效；
  // 简化为永不删除参数——只在有选中会话时写入。已删会话的陈旧 ?s=
  // 由恢复 effect 的存在性检查自然忽略。）
  useEffect(() => {
    const sid = state.currentSessionId;
    if (!sid) return;
    const url = new URL(window.location.href);
    url.searchParams.set("s", sid);
    window.history.replaceState(null, "", url);
  }, [state.currentSessionId]);

  const inspector = (drawerMode = false) => (
    <div
      className={drawerMode ? "inspector drawer-inspector" : "inspector"}
      data-testid="inspector"
    >
      <div className="tabbar">
        <button
          className={state.inspectorTab === "run" ? "on" : ""}
          onClick={() => actions.setInspectorTab("run")}
        >
          <IconRun size={10} color="var(--c-agent)" /> Run
        </button>
      </div>
      <RunInspector />
    </div>
  );

  // 记忆模式：主区整体切换（rail 保留，chat + inspector 暂离——design.md 决策 5）
  if (state.mainView === "memory") {
    if (narrow) {
      return (
        <div className="shell narrow">
          <MemoryExplorer />
        </div>
      );
    }
    return (
      <div className="shell" data-narrow={narrow ? "1" : "0"}>
        <SessionRail />
        <MemoryExplorer />
        {crtOn && <div className="crt-overlay" data-testid="crt-overlay" />}
      </div>
    );
  }

  if (narrow) {
    return (
      <div className="shell narrow">
        <div className="chat">
          <div className="statusbar">
            <button className="drawer-toggle" onClick={() => setDrawer(drawer === "sessions" ? null : "sessions")}>
              会话
            </button>
            <button
              className="drawer-toggle"
              onClick={() => {
                setDrawer(drawer === "run" ? null : "run");
                actions.setInspectorTab("run");
              }}
            >
              Run
            </button>
            <button
              className="drawer-toggle"
              onClick={() => {
                setDrawer(null);
                actions.setMainView("memory");
              }}
            >
              Memory
            </button>
            <span className="dot-label">
              {state.status ? state.status.model : state.statusError ? "网关不可用" : "…"}
            </span>
          </div>
          {drawer === "sessions" && <SessionRail drawer />}
          {drawer === "run" && inspector(true)}
          {drawer === "memory" && inspector(true)}
          <Conversation />
        </div>
      </div>
    );
  }

  return (
    <div className="shell" data-narrow={narrow ? "1" : "0"}>
      <SessionRail />
      <div className="chat">
        <div className="statusbar" data-testid="statusbar">
          <span className="dot" />
          <span className="dot-label" data-testid="model-name">
            {state.status ? state.status.model : state.statusError ? "网关不可用" : "…"}
          </span>
          {state.status?.mode && <span className="badge">{state.status.mode}</span>}
          <button
            className="crt-toggle"
            onClick={toggleTheme}
            title={theme === "dark" ? "切换到浅色" : "切换到深色"}
            data-testid="theme-toggle"
          >
            {theme === "dark" ? <IconSun size={12} /> : <IconMoon size={12} />}
          </button>
          <button
            className={`crt-toggle${crtOn ? " on" : ""}`}
            onClick={() => setCrtOn(!crtOn)}
            disabled={crtForcedOff}
            title={crtOn ? "关闭 CRT 效果" : "开启 CRT 效果"}
            data-testid="crt-toggle"
          >
            <IconCrt size={12} /> CRT
          </button>
          {state.status?.skills && state.status.skills.length > 0 && (
            <span className="badge">{state.status.skills.length} skills</span>
          )}
          {state.status?.mcp && state.status.mcp.length > 0 && (
            <span className="badge">{state.status.mcp.length} MCP</span>
          )}
          {state.currentSessionId && (
            <button
              className="px-btn-secondary"
              onClick={() => {
                const session = state.sessions.find(
                  (s) => s.session_id === state.currentSessionId,
                );
                if (session) actions.openMemoryForThread(session.thread_id);
              }}
              data-testid="session-memories"
            >
              本会话记忆
            </button>
          )}
        </div>
        <Conversation />
      </div>
      {inspector()}
      {crtOn && <div className="crt-overlay" data-testid="crt-overlay" />}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
