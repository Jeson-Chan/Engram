/** Configs 面板（web-config-surface）— inspector 第三 tab。
 *
 * 草稿态编辑 + 底部单一"应用"按钮：一次提交技能启停 / override / 三运行旋钮 /
 * 模型与模式 / 思考显示；成功 toast "已生效!"，失败提示并保留草稿。
 * MCP 为重载按钮（独立操作，不进 apply 链）——skills 与 MCP 仅在此展示
 * （composer 旁 chips 已移除）。
 *
 * testid 契约：configs-panel / configs-apply / configs-toast /
 * cfg-model / cfg-model-input / cfg-mode / cfg-mcp-reload / cfg-thinking /
 * skill-row-{name} / skill-toggle-{name} / skill-override-{name} /
 * rounds-input / rounds-clear / effort-select / window-input / window-clear。
 */
import { useEffect, useState } from "react";
import { useApp } from "../store";
import type { ConfigDraft } from "../store";

/** provider → kind（思考强度支持性标注；与后端 provider_profile 一致）。 */
const OPENAI_COMPAT = new Set([
  "openai", "qwen", "moonshot", "openrouter", "xai", "zhipu", "nvidia",
]);
function providerKindOf(provider: string | null | undefined): string {
  if (!provider) return "unknown";
  if (OPENAI_COMPAT.has(provider)) return "openai_compat";
  if (provider === "anthropic" || provider === "gemini") return provider;
  if (provider === "deepseek" || provider === "ollama") return provider;
  return "unknown";
}

export function ConfigsPanel() {
  const { state, actions } = useApp();
  const draft = state.configDraft;
  const status = state.status;
  const [roundsLocal, setRoundsLocal] = useState(
    state.knobs.maxLoopSteps != null ? String(state.knobs.maxLoopSteps) : "",
  );
  const [windowLocal, setWindowLocal] = useState(
    state.knobs.contextWindow != null ? String(state.knobs.contextWindow) : "",
  );
  const [knobError, setKnobError] = useState<string | null>(null);

  useEffect(() => {
    actions.refreshSkills();
  }, [actions]);

  // toast 自动消失
  useEffect(() => {
    if (!state.configToast) return;
    const t = setTimeout(() => actions.clearConfigToast(), 2500);
    return () => clearTimeout(t);
  }, [state.configToast, actions]);

  const setDraft = (patch: Partial<ConfigDraft>) => actions.setConfigDraft(patch);

  // ---- 旋钮输入（ui-polish-3）：框即当前值，直接改，应用时校验生效 ----
  // 外部变化（应用成功重置草稿 / 自动按钮）→ 同步框内文本
  useEffect(() => {
    const v = draft.maxLoopSteps !== undefined ? draft.maxLoopSteps : state.knobs.maxLoopSteps;
    setRoundsLocal(v != null ? String(v) : "");
  }, [draft.maxLoopSteps, state.knobs.maxLoopSteps]);
  useEffect(() => {
    const v = draft.contextWindow !== undefined ? draft.contextWindow : state.knobs.contextWindow;
    setWindowLocal(v != null ? String(v) : "");
  }, [draft.contextWindow, state.knobs.contextWindow]);

  const editRounds = (v: string) => {
    setRoundsLocal(v);
    if (v.trim() === "") {
      setKnobError(null);
      setDraft({ maxLoopSteps: null }); // 清空 = auto
      return;
    }
    const n = Number(v);
    if (Number.isInteger(n) && n >= 1) {
      setKnobError(null);
      setDraft({ maxLoopSteps: n });
    } else {
      setKnobError(`轮数需为 ≥1 整数（当前输入：${v}）`);
    }
  };
  const editWindow = (v: string) => {
    setWindowLocal(v);
    if (v.trim() === "") {
      setKnobError(null);
      setDraft({ contextWindow: null });
      return;
    }
    const n = Number(v);
    if (Number.isInteger(n) && n >= 1000) {
      setKnobError(null);
      setDraft({ contextWindow: n });
    } else {
      setKnobError(`窗口需为 ≥1000 的 token 数（当前输入：${v}）`);
    }
  };

  // ---- 草稿 / 已应用值的取值 ----
  const skillEnabled = (id: string, applied: boolean) =>
    draft.skills?.[id] ?? applied;
  const toggleSkill = (id: string, applied: boolean) =>
    setDraft({ skills: { ...(draft.skills ?? {}), [id]: !skillEnabled(id, applied) } });

  const overrideNames = draft.override ?? state.skillOverride;
  // 已应用值（来源标记用）与草稿值（输入控件用）分开
  const appliedRounds = state.knobs.maxLoopSteps;
  const appliedEffort = state.knobs.reasoningEffort;
  const appliedWindow = state.knobs.contextWindow;
  const effortValue =
    draft.reasoningEffort !== undefined ? draft.reasoningEffort : appliedEffort;
  const pendingHint = (dirtyValue: unknown) =>
    dirtyValue !== undefined ? "（待应用）" : "";
  const providerValue = draft.provider ?? status?.provider ?? "";
  const modeValue = draft.mode ?? (status?.mode === "expert" ? "expert" : "lightweight");
  const thinkingValue = draft.thinkingVisible ?? state.thinkingVisible;
  const kind = providerKindOf(providerValue || status?.provider);
  const effortSupported = ["openai_compat", "anthropic", "gemini"].includes(kind);
  const dirty = Object.keys(draft).length > 0;

  const mcp = status?.mcp ?? [];
  const models = status?.models ?? [];

  return (
    <div className="configs-panel" data-testid="configs-panel">
      {/* ---- 模型与模式 ---- */}
      <div className="knobs-title">模型与模式（作用于网关全局，仅影响后续运行）</div>
      <div className="knob-row" data-testid="cfg-model-row">
        <label>模型 provider</label>
        <select
          value={providerValue}
          onChange={(e) => setDraft({ provider: e.target.value || null })}
          data-testid="cfg-model"
        >
          <option value="">（当前：{status?.model ?? "未知"}）</option>
          {models.map((m) => (
            <option key={m.provider} value={m.provider}>
              {m.provider}（{m.model}）
            </option>
          ))}
        </select>
        <input
          placeholder="model（可选）"
          value={draft.model ?? ""}
          onChange={(e) => setDraft({ model: e.target.value || null })}
          data-testid="cfg-model-input"
        />
      </div>
      <div className="knob-row" data-testid="cfg-mode-row">
        <label>模式</label>
        <select
          value={modeValue}
          onChange={(e) => setDraft({ mode: e.target.value as "expert" | "lightweight" })}
          data-testid="cfg-mode"
        >
          <option value="lightweight">lightweight</option>
          <option value="expert">expert</option>
        </select>
      </div>

      {/* ---- 技能 ---- */}
      <div className="knobs-title">技能</div>
      {state.skillsError && (
        <div className="notice" data-testid="skill-panel-error">⚠ {state.skillsError}</div>
      )}
      {state.skills.length === 0 && !state.skillsError && (
        <div className="empty">Skill 模块未启用或无激活 skill</div>
      )}
      {state.skills.map((s) => {
        const enabled = skillEnabled(s.skill_id, s.enabled);
        const isOverridden = overrideNames.includes(s.name);
        return (
          <div className="config-row" key={s.skill_id} data-testid={`skill-row-${s.name}`}>
            <span className="cfg-name">{s.name}</span>
            <span className="cfg-meta">
              {(s.effective_rate * 100).toFixed(0)}% · 选中 {s.total_selections}
            </span>
            {s.description && <span className="cfg-desc">{s.description}</span>}
            <button
              className={`px-btn-secondary${enabled ? " on" : ""}`}
              data-testid={`skill-toggle-${s.name}`}
              onClick={() => toggleSkill(s.skill_id, s.enabled)}
            >
              {enabled ? "已启用" : "已禁用"}
            </button>
            <button
              className={`px-btn-secondary${isOverridden ? " on" : ""}`}
              data-testid={`skill-override-${s.name}`}
              onClick={() =>
                setDraft({
                  override: isOverridden ? [] : [s.name],
                })
              }
            >
              {isOverridden ? "override 中" : "设为 override"}
            </button>
          </div>
        );
      })}

      {/* ---- 运行参数 ---- */}
      <div className="knobs-title">运行参数（会话级）</div>
      <div className="knob-row" data-testid="knob-rounds">
        <label>轮数上限</label>
        <input
          type="number" min={1} placeholder="auto"
          value={roundsLocal}
          onChange={(e) => editRounds(e.target.value)}
          data-testid="rounds-input"
        />
        <button className="px-btn-secondary" onClick={() => { setKnobError(null); setDraft({ maxLoopSteps: null }); }} data-testid="rounds-clear">自动</button>
        <small data-testid="rounds-source">
          {appliedRounds ? `manual：${appliedRounds}` : "auto（配置默认）"}
          {pendingHint(draft.maxLoopSteps)}
        </small>
      </div>
      <div className="knob-row" data-testid="knob-effort">
        <label>思考强度</label>
        <select
          value={effortValue ?? "off"}
          onChange={(e) => {
            const v = e.target.value;
            setDraft({ reasoningEffort: v === "off" ? null : (v as "low" | "medium" | "high") });
          }}
          data-testid="effort-select"
        >
          <option value="off">off（默认）</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <small data-testid="effort-source">
          {appliedEffort ? `manual：${appliedEffort}` : "auto（provider 默认）"}
          {pendingHint(draft.reasoningEffort)}
          {!effortSupported && " · 当前 provider 不支持"}
        </small>
      </div>
      <div className="knob-row" data-testid="knob-window">
        <label>窗口（token）</label>
        <input
          type="number" min={1000} placeholder="auto"
          value={windowLocal}
          onChange={(e) => editWindow(e.target.value)}
          data-testid="window-input"
        />
        <button className="px-btn-secondary" onClick={() => { setKnobError(null); setDraft({ contextWindow: null }); }} data-testid="window-clear">自动</button>
        <small data-testid="window-source">
          {appliedWindow ? `manual：${appliedWindow} tok` : "auto（模型查表）"}
          {pendingHint(draft.contextWindow)}
          · 仅影响压缩时机
        </small>
      </div>
      {knobError && (
        <div className="notice" data-testid="knob-error">⚠ {knobError}</div>
      )}

      {/* ---- MCP ---- */}
      <div className="knobs-title">MCP</div>
      <div className="config-row" data-testid="cfg-mcp-list">
        {mcp.length === 0
          ? <span className="cfg-meta">（未配置 MCP server）</span>
          : mcp.map((m) => (
              <span key={String(m.name)} className="cfg-meta">
                {String(m.name)} · {String(m.transport ?? "")} · {Number(m.tool_count ?? 0)} tools · {String(m.health_state ?? "?")}
              </span>
            ))}
      </div>
      <div className="knob-row">
        <button className="px-btn-secondary" onClick={() => actions.reloadMcp()} data-testid="cfg-mcp-reload">
          重载 MCP
        </button>
      </div>

      {/* ---- 显示 ---- */}
      <div className="knobs-title">显示</div>
      <div className="knob-row" data-testid="cfg-thinking-row">
        <label>思考折叠行</label>
        <button
          className={`px-btn-secondary${thinkingValue ? " on" : ""}`}
          onClick={() => setDraft({ thinkingVisible: !thinkingValue })}
          data-testid="cfg-thinking"
        >
          {thinkingValue ? "显示中" : "已隐藏"}
        </button>
      </div>

      {/* ---- 应用 ---- */}
      <div className="configs-footer">
        <button
          className="px-btn"
          disabled={!dirty}
          onClick={() => actions.applyConfig()}
          data-testid="configs-apply"
        >
          应用{dirty ? "（有待应用修改）" : ""}
        </button>
        {state.configToast && (
          <div className={`configs-toast ${state.configToast.kind}`} data-testid="configs-toast">
            {state.configToast.text}
          </div>
        )}
      </div>
    </div>
  );
}