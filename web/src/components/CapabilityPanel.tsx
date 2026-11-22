/** 能力矩阵（CapabilityPanel）— Inspector 第三 tab，engram doctor 同源只读展示。
 *
 * 数据来自 GET /capabilities（doctor.build_report），绝不含密钥；
 * 探测含网络检查（秒级）——切到本 tab 时按需拉取，不随 App mount 请求。
 */

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { useApp } from "../store";
import { IconRun, IconAnalytics } from "./pixel-icons";
import type { CapabilityRow, ConnectivityRow } from "../lib/types";

const STATE_MARK: Record<string, { symbol: string; cls: string }> = {
  on: { symbol: "●", cls: "ok" },
  off: { symbol: "○", cls: "off" },
  broken: { symbol: "✕", cls: "fail" },
  ok: { symbol: "●", cls: "ok" },
  fail: { symbol: "✕", cls: "fail" },
  skipped: { symbol: "-", cls: "off" },
};

function CapRow({ row, kind }: { row: CapabilityRow | ConnectivityRow; kind: "cap" | "conn" }) {
  const mark = STATE_MARK[row.state] ?? { symbol: "?", cls: "off" };
  return (
    <div className="cap-row" data-testid={`${kind}-${row.key}`} data-state={row.state}>
      <div className="cap-state">
        <span className={`st ${mark.cls}`}>{mark.symbol} {row.state}</span>
        <span className="cap-label">{row.label}</span>
      </div>
      <div className="cap-detail">
        {row.detail}
        {"fix" in row && row.fix && row.state === "broken" && (
          <span className="cap-fix">修复：{row.fix}</span>
        )}
      </div>
    </div>
  );
}

export function CapabilityPanel() {
  const { state, actions } = useApp();
  const report = state.capabilities;
  const [helpOpen, setHelpOpen] = useState(false);

  // 切到本 tab 时按需拉取（数据为空且无错误 → 首次）
  useEffect(() => {
    if (!state.capabilities && !state.capabilitiesError) {
      actions.refreshCapabilities();
    }
  }, [state.inspectorTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div data-testid="capability-panel">
      <div className="px-panel-bar" style={{ "--bar-c": "var(--c-agent)" } as CSSProperties}>
        <IconAnalytics size={17} color="#fff" /> 能力矩阵
        {report?.has_broken && <span className="st fail" style={{ marginLeft: "auto" }}>有 broken 项</span>}
      </div>

      {report && (
        <div className="cap-row" data-testid="cap-deployment" data-state="ok">
          <div className="cap-state">
            <span className="cap-label">运行环境</span>
          </div>
          <div className="cap-detail">
            {report.deployment === "docker"
              ? "docker 容器内——记忆层由 compose 注入，.env 无需配置记忆"
              : "宿主机直跑（venv）——默认 Markdown 记忆；分层需自行配置 Redis/PG"}
          </div>
        </div>
      )}

      {!report && !state.capabilitiesError && (
        <div className="empty">探测中…（连通性检查需数秒）</div>
      )}
      {!report && state.capabilitiesError && (
        <div className="empty" data-testid="capabilities-error">
          能力数据不可用：{state.capabilitiesError}
          {/404/.test(state.capabilitiesError) && (
            <div style={{ marginTop: 8 }}>
              网关里没有 /capabilities 路由——gateway 是旧版本。
              venv 直跑请重启网关；docker 部署请 `docker compose up -d --build gateway`。
            </div>
          )}
        </div>
      )}

      {report && (
        <>
          {report.capabilities.map((row) => (
            <CapRow key={row.key} row={row} kind="cap" />
          ))}
          <div className="px-panel-bar" style={{ "--bar-c": "var(--c-agent)" } as CSSProperties}>
            <IconRun size={11} color="#fff" /> 连通性检查
          </div>
          {report.connectivity.map((row) => (
            <CapRow key={row.key} row={row} kind="conn" />
          ))}
          {helpOpen && (
            <div data-testid="capability-help" style={{ padding: "0 12px 6px" }}>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                与 TUI `engram doctor` 同一份报告；off = 未启用（附原因），broken = 已启用但缺依赖。
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }} data-testid="config-tui-only-note">
                配置仅可在 TUI 中修改（/guide 或 Ctrl+B）——Web 端为只读展示；
                gateway 只在启动时读取 .env，改动需重启对应后端（venv 重启进程 / docker 重建镜像）。
              </div>
            </div>
          )}
          <div style={{ padding: "0 12px 10px" }}>
            <button
              className="px-btn-secondary"
              onClick={() => setHelpOpen((v) => !v)}
              data-testid="capability-help-toggle"
              style={{ fontSize: 12, padding: "2px 10px" }}
            >
              ? 帮助{helpOpen ? "（收起）" : ""}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
