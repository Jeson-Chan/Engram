/** Skill 管理面板（web-skill-override）— inspector "Skills" tab。
 *
 * 数据源 GET /skills；启停 POST /skills/{id}/enabled（失败提示 + 回滚）；
 * override 单选（会话级，随 chat 请求携带）/ 清除。testid 契约：
 * skill-panel / skill-row-{name} / skill-toggle-{name} / skill-override-{name} /
 * skill-override-clear / skill-panel-error。
 */
import { useEffect } from "react";
import { useApp } from "../store";

export function SkillPanel() {
  const { state, actions } = useApp();

  useEffect(() => {
    actions.refreshSkills();
  }, [actions]);

  const override = state.skillOverride;

  return (
    <div className="skill-panel" data-testid="skill-panel">
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
