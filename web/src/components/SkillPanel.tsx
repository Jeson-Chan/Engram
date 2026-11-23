/** Skill 管理面板（web-skill-override）— inspector "Skills" tab。
 *
 * 数据源 GET /skills；启停 POST /skills/{id}/enabled（失败提示 + 回滚）；
 * override 单选（会话级，随 chat 请求携带）/ 清除。testid 契约：
 * skill-panel / skill-row-{name} / skill-toggle-{name} / skill-override-{name} /
 * skill-override-clear / skill-panel-error。
 */
import { useEffect, useState } from "react";
import { useApp } from "../store";

/** provider → kind（与后端 provider_profile 一致；仅用于思考强度支持性标注）。 */
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

/** 运行参数区（runtime-knobs）：三旋钮 + 当前值/来源（manual / auto）。 */
function RuntimeKnobsSection() {
  const { state, actions } = useApp();
  const knobs = state.knobs;
  const kind = providerKindOf(state.status?.provider);
  const effortSupported = ["openai_compat", "anthropic", "gemini"].includes(kind);
  const [roundsDraft, setRoundsDraft] = useState("");
  const [windowDraft, setWindowDraft] = useState("");

  const applyRounds = () => {
    const n = Number(roundsDraft);
    if (!Number.isInteger(n) || n < 1) return;
    actions.setKnobs({ maxLoopSteps: n });
    setRoundsDraft("");
  };
  const applyWindow = () => {
    const n = Number(windowDraft);
    if (!Number.isInteger(n) || n < 1000) return;
    actions.setKnobs({ contextWindow: n });
    setWindowDraft("");
  };

  return (
    <div className="runtime-knobs" data-testid="runtime-knobs">
      <div className="knobs-title">运行参数（会话级，随请求携带）</div>

      <div className="knob-row" data-testid="knob-rounds">
        <label>搜索/工具轮数上限</label>
        <input
          type="number" min={1} placeholder="auto"
          value={roundsDraft}
          onChange={(e) => setRoundsDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && applyRounds()}
          data-testid="rounds-input"
        />
        <button className="px-btn-secondary" onClick={applyRounds} data-testid="rounds-apply">应用</button>
        <button
          className="px-btn-secondary"
          onClick={() => actions.setKnobs({ maxLoopSteps: null })}
          data-testid="rounds-clear"
        >
          自动
        </button>
        <small data-testid="rounds-source">
          {knobs.maxLoopSteps ? `manual：${knobs.maxLoopSteps} 轮` : "auto（配置默认）"}
        </small>
      </div>

      <div className="knob-row" data-testid="knob-effort">
        <label>思考强度</label>
        <select
          value={knobs.reasoningEffort ?? "off"}
          onChange={(e) => {
            const v = e.target.value;
            actions.setKnobs({ reasoningEffort: v === "off" ? null : (v as "low" | "medium" | "high") });
          }}
          data-testid="effort-select"
        >
          <option value="off">off（provider 默认）</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <small data-testid="effort-source">
          {knobs.reasoningEffort ? `manual：${knobs.reasoningEffort}` : "auto（provider 默认）"}
          {!effortSupported && " · 当前 provider 不支持"}
        </small>
      </div>

      <div className="knob-row" data-testid="knob-window">
        <label>上下文窗口（token）</label>
        <input
          type="number" min={1000} placeholder="auto"
          value={windowDraft}
          onChange={(e) => setWindowDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && applyWindow()}
          data-testid="window-input"
        />
        <button className="px-btn-secondary" onClick={applyWindow} data-testid="window-apply">应用</button>
        <button
          className="px-btn-secondary"
          onClick={() => actions.setKnobs({ contextWindow: null })}
          data-testid="window-clear"
        >
          自动
        </button>
        <small data-testid="window-source">
          {knobs.contextWindow ? `manual：${knobs.contextWindow} tok` : "auto（模型查表）"}
          · 仅影响压缩时机，不改变模型真实上限
        </small>
      </div>
    </div>
  );
}

export function SkillPanel() {
  const { state, actions } = useApp();

  useEffect(() => {
    actions.refreshSkills();
  }, [actions]);

  const override = state.skillOverride;

  return (
    <div className="skill-panel" data-testid="skill-panel">
      <RuntimeKnobsSection />
      <div className="knobs-title">Skills</div>
      {state.skillsError && (
        <div className="notice" data-testid="skill-panel-error">
          ⚠ {state.skillsError}
        </div>
      )}
      {state.skills.length === 0 && !state.skillsError && (
        <div className="empty">
          Skill 模块未启用或无激活 skill
          <br />
          <small>CLI/TUI 可用 /skill install 安装</small>
        </div>
      )}
      {state.skills.map((s) => {
        const isOverridden = override.includes(s.name);
        return (
          <div className="skill-row" key={s.skill_id} data-testid={`skill-row-${s.name}`}>
            <div className="skill-main">
              <span className="skill-name">{s.name}</span>
              <span className="skill-meta">
                生效率 {(s.effective_rate * 100).toFixed(0)}% · 选中 {s.total_selections}
              </span>
              {s.description && <span className="skill-desc">{s.description}</span>}
            </div>
            <div className="skill-ops">
              <button
                className={`px-btn-secondary skill-toggle${s.enabled ? " on" : ""}`}
                data-testid={`skill-toggle-${s.name}`}
                title={s.enabled ? "禁用该 skill" : "启用该 skill"}
                onClick={() => {
                  actions.setSkillEnabled(s.skill_id, !s.enabled);
                }}
              >
                {s.enabled ? "已启用" : "已禁用"}
              </button>
              <button
                className={`px-btn-secondary skill-override${isOverridden ? " on" : ""}`}
                data-testid={`skill-override-${s.name}`}
                title={isOverridden ? "清除 override" : "每轮强制选中该 skill"}
                onClick={() => {
                  actions.setSkillOverride(isOverridden ? [] : [s.name]);
                }}
              >
                {isOverridden ? "override 中" : "设为 override"}
              </button>
            </div>
          </div>
        );
      })}
      {override.length > 0 && (
        <button
          className="px-btn-secondary skill-override-clear"
          data-testid="skill-override-clear"
          onClick={() => actions.setSkillOverride([])}
        >
          清除 override（{override.join(", ")}）
        </button>
      )}
    </div>
  );
}
