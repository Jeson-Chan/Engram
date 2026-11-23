"""`engram doctor` — 能力三态矩阵（on / off(原因) / broken(缺什么)）+ 连通性检查。

单一数据源（D5）：CLI 表格与 TUI `Ctrl+U` Inspector 面板都消费
`build_report()` 返回的同一份 `DoctorReport`。

判定只读显式配置（`.env` / compose environment），不重新推断：
- 只读类功能依赖就位 → on；依赖缺席 → off（附原因）。
- 权力授予类（MCP、沙箱）未授权 → off；已授权但缺依赖 → broken。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from rich.console import Console
from rich.table import Table
from rich.text import Text

from engram.backend.app.cli.probes import ProbeResult, probe_all

CapabilityState = Literal["on", "off", "broken"]
ConnectivityState = Literal["ok", "fail", "skipped"]

_LOCAL_SANDBOX = (
    "engram.backend.agents.sandbox.local.local_sandbox_provider:LocalSandboxProvider"
)
_DOCKER_SANDBOX = (
    "engram.backend.agents.sandbox.docker.docker_sandbox_provider:DockerSandboxProvider"
)


@dataclass(frozen=True)
class Capability:
    """功能能力行。state=broken 时 detail/fix 必须说明缺什么、怎么修。"""

    key: str
    label: str
    state: CapabilityState
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class Connectivity:
    """连通性检查行。skipped = 该功能未配置，无需检查。"""

    key: str
    label: str
    state: ConnectivityState
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    capabilities: tuple[Capability, ...]
    connectivity: tuple[Connectivity, ...]
    deployment: str = "venv"  # "docker" | "venv"——guide/前端据此决定记忆层指引

    @property
    def has_broken(self) -> bool:
        return any(cap.state == "broken" for cap in self.capabilities)

    def to_dict(self) -> dict:
        return {
            "deployment": self.deployment,
            "capabilities": [
                {
                    "key": c.key,
                    "label": c.label,
                    "state": c.state,
                    "detail": c.detail,
                    "fix": c.fix,
                }
                for c in self.capabilities
            ],
            "connectivity": [
                {
                    "key": c.key,
                    "label": c.label,
                    "state": c.state,
                    "detail": c.detail,
                }
                for c in self.connectivity
            ],
        }


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or "").strip()


def _env_true(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() == "true"


def _probe(probes: Mapping[str, ProbeResult], name: str) -> ProbeResult | None:
    return probes.get(name)


def _connectivity_probe(
    probes: Mapping[str, ProbeResult],
    name: str,
    label: str,
    *,
    configured: bool,
    unconfigured_detail: str,
) -> Connectivity:
    result = _probe(probes, name)
    if not configured:
        return Connectivity(name, label, "skipped", unconfigured_detail)
    if result is None:
        return Connectivity(name, label, "fail", "探测未执行")
    return Connectivity(
        name, label, "ok" if result.available else "fail", result.detail,
    )


def build_report(
    project_root: Path,
    *,
    probes: Mapping[str, ProbeResult] | None = None,
) -> DoctorReport:
    """构建能力矩阵与连通性检查（可注入探测结果供测试）。"""
    probe_results = probes if probes is not None else probe_all(Path(project_root))
    capabilities: list[Capability] = []

    # ---- 只读 / 计算类 ----
    llm = _probe(probe_results, "llm")
    if llm is not None and llm.available:
        capabilities.append(Capability("llm", "对话（LLM）", "on", llm.detail))
    else:
        detail = llm.detail if llm is not None else "无法确定 LLM 可用性"
        fix = (llm.fix if llm is not None else "") or "运行 engram init 或设置 provider API Key"
        capabilities.append(Capability("llm", "对话（LLM）", "broken", detail, fix))

    memory_use = _env("ENGRAM_MEMORY_USE")
    if memory_use:
        capabilities.append(
            Capability("memory", "长期记忆（Markdown）", "on", f"MemoryProvider={memory_use}")
        )
    else:
        capabilities.append(Capability(
            "memory", "长期记忆（Markdown）", "off",
            "未设置 ENGRAM_MEMORY_USE", "运行 engram init（会写入 default）",
        ))

    redis_url = _env("ENGRAM_REDIS_URL")
    redis_probe = _probe(probe_results, "redis")
    if not redis_url:
        # web-config-surface：off 说明精简为一句
        capabilities.append(Capability(
            "memory_hot", "记忆热层（Redis）", "off",
            "未配置 ENGRAM_REDIS_URL——默认单层存储，功能不受影响",
        ))
    elif redis_probe is not None and redis_probe.available:
        capabilities.append(Capability("memory_hot", "记忆热层（Redis）", "on", redis_probe.detail))
    else:
        capabilities.append(Capability(
            "memory_hot", "记忆热层（Redis）", "broken",
            redis_probe.detail if redis_probe is not None else "Redis 探测未执行",
            (redis_probe.fix if redis_probe is not None else "") or "启动 Redis",
        ))

    pg_dsn = _env("ENGRAM_MEMORY_PG_DSN")
    pg_probe = _probe(probe_results, "pg")
    if not pg_dsn:
        # web-config-surface：off 说明精简为一句
        capabilities.append(Capability(
            "memory_cold", "记忆冷层（Postgres）", "off",
            "未配置 ENGRAM_MEMORY_PG_DSN——默认单层存储，功能不受影响",
        ))
    elif pg_probe is not None and pg_probe.available:
        capabilities.append(Capability("memory_cold", "记忆冷层（Postgres）", "on", pg_probe.detail))
    else:
        capabilities.append(Capability(
            "memory_cold", "记忆冷层（Postgres）", "broken",
            pg_probe.detail if pg_probe is not None else "Postgres 探测未执行",
            (pg_probe.fix if pg_probe is not None else "") or "启动 Postgres",
        ))

    phase2 = _env_true("ENGRAM_MEMORY_PHASE2_ENABLED")
    if not phase2:
        capabilities.append(Capability(
            "memory_phase2", "自动记忆沉淀（后台巩固）", "off",
            "ENGRAM_MEMORY_PHASE2_ENABLED=false",
        ))
    elif not memory_use:
        capabilities.append(Capability(
            "memory_phase2", "自动记忆沉淀（后台巩固）", "broken",
            "Phase 2 已开启但记忆主 Provider 未启用", "设置 ENGRAM_MEMORY_USE=default",
        ))
    else:
        capabilities.append(Capability(
            "memory_phase2", "自动记忆沉淀（后台巩固）", "on", "每 N 轮自动抽取 + 巩固",
        ))

    if _env_true("ENGRAM_SKILL_ENABLED"):
        capabilities.append(Capability("skill", "Skill 注入", "on", "Skill 模块已启用"))
    else:
        capabilities.append(Capability(
            "skill", "Skill 注入", "off", "ENGRAM_SKILL_ENABLED=false",
            "运行 engram init 或设 ENGRAM_SKILL_ENABLED=true",
        ))

    web_dist = _probe(probe_results, "web_dist")
    if _env_true("ENGRAM_WEB_UI_ENABLED"):
        if web_dist is not None and web_dist.available:
            capabilities.append(Capability("web_ui", "Web 工作台", "on", web_dist.detail))
        else:
            capabilities.append(Capability(
                "web_ui", "Web 工作台", "broken",
                "已开启但前端构建产物缺失",
                (web_dist.fix if web_dist is not None else "") or "cd web && npm run build",
            ))
    else:
        capabilities.append(Capability(
            "web_ui", "Web 工作台", "off", "ENGRAM_WEB_UI_ENABLED 未开启",
        ))

    if _env_true("ENGRAM_MULTIAGENT_ENABLED", default=True):
        capabilities.append(Capability("multiagent", "MultiAgent 委派", "on", "已启用"))
    else:
        capabilities.append(Capability("multiagent", "MultiAgent 委派", "off", "已显式关闭"))

    tavily_key = _env("TAVILY_API_KEY")
    tavily_probe = _probe(probe_results, "tavily")
    if tavily_key and tavily_probe is not None and tavily_probe.available:
        capabilities.append(Capability("tavily", "Tavily 联网搜索", "on", tavily_probe.detail))
    elif not tavily_key:
        capabilities.append(Capability(
            "tavily", "Tavily 联网搜索", "off",
            "未配置 TAVILY_API_KEY，搜索回退 DuckDuckGo",
        ))
    else:
        capabilities.append(Capability(
            "tavily", "Tavily 联网搜索", "off",
            "Tavily 端点不可达，搜索回退 DuckDuckGo",
        ))

    # ---- 权力授予类（未授权 = off；已授权但缺依赖 = broken）----
    if _env_true("ENGRAM_MCP_ENABLED"):
        mcp_probe = _probe(probe_results, "mcp_config")
        if mcp_probe is not None and mcp_probe.available:
            capabilities.append(Capability("mcp", "MCP 工具", "on", mcp_probe.detail))
        else:
            capabilities.append(Capability(
                "mcp", "MCP 工具", "broken",
                mcp_probe.detail if mcp_probe is not None else "MCP 配置探测未执行",
                (mcp_probe.fix if mcp_probe is not None else "") or "创建 .engram/mcp_servers.yaml",
            ))
    else:
        capabilities.append(Capability(
            "mcp", "MCP 工具", "off", "未授权启用（ENGRAM_MCP_ENABLED=false）",
        ))

    sandbox_use = _env("ENGRAM_SANDBOX_USE")
    if not sandbox_use:
        capabilities.append(Capability(
            "sandbox", "沙箱", "off", "未授权启用（ENGRAM_SANDBOX_USE 为空）",
        ))
    elif sandbox_use == _DOCKER_SANDBOX:
        docker_probe = _probe(probe_results, "docker")
        if docker_probe is not None and docker_probe.available:
            capabilities.append(Capability("sandbox", "沙箱（Docker）", "on", docker_probe.detail))
        else:
            capabilities.append(Capability(
                "sandbox", "沙箱（Docker）", "broken",
                docker_probe.detail if docker_probe is not None else "Docker 探测未执行",
                (docker_probe.fix if docker_probe is not None else "") or "启动 Docker daemon",
            ))
    elif sandbox_use == _LOCAL_SANDBOX:
        bash = _env("ENGRAM_SANDBOX_ALLOW_HOST_BASH", "true").lower() != "false"
        capabilities.append(Capability(
            "sandbox", "沙箱（Local）", "on",
            "允许宿主机 bash（无隔离）" if bash else "仅非 bash 工具（已禁用宿主机 bash）",
        ))
    else:
        capabilities.append(Capability(
            "sandbox", "沙箱（自定义 provider）", "on", sandbox_use,
        ))

    # ---- 连通性检查（LLM、Tavily、PG、Redis、Docker、MCP、Node）----
    connectivity: list[Connectivity] = []
    llm_result = _probe(probe_results, "llm")
    connectivity.append(Connectivity(
        "llm", "LLM", "ok" if llm_result is not None and llm_result.available else "fail",
        llm_result.detail if llm_result is not None else "探测未执行",
    ))
    tavily_result = _probe(probe_results, "tavily")
    if not tavily_key:
        connectivity.append(Connectivity(
            "tavily", "Tavily", "skipped", "未配置（搜索回退 DuckDuckGo）",
        ))
    else:
        connectivity.append(Connectivity(
            "tavily", "Tavily",
            "ok" if tavily_result is not None and tavily_result.available else "fail",
            tavily_result.detail if tavily_result is not None else "探测未执行",
        ))
    connectivity.append(_connectivity_probe(
        probe_results, "pg", "Postgres", configured=bool(pg_dsn),
        unconfigured_detail="未配置（Markdown 记忆）",
    ))
    connectivity.append(_connectivity_probe(
        probe_results, "redis", "Redis", configured=bool(redis_url),
        unconfigured_detail="未配置（Markdown 记忆）",
    ))
    docker_result = _probe(probe_results, "docker")
    connectivity.append(Connectivity(
        "docker", "Docker",
        "ok" if docker_result is not None and docker_result.available else "fail",
        docker_result.detail if docker_result is not None else "探测未执行",
    ))
    mcp_result = _probe(probe_results, "mcp_config")
    if not _env_true("ENGRAM_MCP_ENABLED"):
        connectivity.append(Connectivity("mcp", "MCP", "skipped", "未授权启用"))
    else:
        connectivity.append(Connectivity(
            "mcp", "MCP",
            "ok" if mcp_result is not None and mcp_result.available else "fail",
            mcp_result.detail if mcp_result is not None else "探测未执行",
        ))
    node_result = _probe(probe_results, "node")
    connectivity.append(Connectivity(
        "node", "Node.js",
        "ok" if node_result is not None and node_result.available else "fail",
        node_result.detail if node_result is not None else "探测未执行",
    ))

    deployment_probe = _probe(probe_results, "deployment")
    deployment = "docker" if (deployment_probe is not None and deployment_probe.available) else "venv"

    return DoctorReport(tuple(capabilities), tuple(connectivity), deployment=deployment)


_STATE_STYLE = {
    "on": ("●", "green"),
    "off": ("○", "dim"),
    "broken": ("✕", "red"),
    "ok": ("●", "green"),
    "fail": ("✕", "red"),
    "skipped": ("-", "dim"),
}

_STATE_LABEL = {
    "on": "on",
    "off": "off",
    "broken": "broken",
    "ok": "ok",
    "fail": "fail",
    "skipped": "skipped",
}


def render_report(report: DoctorReport, console: Console | None = None) -> None:
    """渲染两张表（CLI 输出；TUI 复用 build_report 的数据自行绘制）。"""
    console = console or Console()

    deploy_label = "docker 容器（记忆层由 compose 注入）" if report.deployment == "docker" else "宿主机直跑（venv）"
    console.print(f"[cyan]运行环境[/cyan]：{deploy_label}")

    cap_table = Table(title="能力矩阵", show_lines=False)
    cap_table.add_column("功能", style="cyan")
    cap_table.add_column("状态")
    cap_table.add_column("说明 / 修复建议")
    for cap in report.capabilities:
        symbol, style = _STATE_STYLE[cap.state]
        status = Text(f"{symbol} {_STATE_LABEL[cap.state]}", style=style)
        detail = cap.detail + (f"\n修复：{cap.fix}" if cap.fix and cap.state == "broken" else "")
        cap_table.add_row(cap.label, status, detail)
    console.print(cap_table)

    conn_table = Table(title="连通性检查", show_lines=False)
    conn_table.add_column("检查", style="cyan")
    conn_table.add_column("状态")
    conn_table.add_column("说明")
    for item in report.connectivity:
        symbol, style = _STATE_STYLE[item.state]
        conn_table.add_row(
            item.label, Text(f"{symbol} {_STATE_LABEL[item.state]}", style=style), item.detail,
        )
    console.print(conn_table)

    if report.has_broken:
        console.print("[yellow]存在 broken 项：按修复建议处理后重跑 engram doctor。[/yellow]")
    else:
        console.print("[green]未发现 broken 项。[/green]")


def run_doctor(
    project_root: Path,
    *,
    as_json: bool = False,
    probes: Mapping[str, ProbeResult] | None = None,
    console: Console | None = None,
) -> int:
    """`engram doctor` 主流程。broken 项存在时返回 1。"""
    console = console or Console()
    report = build_report(Path(project_root), probes=probes)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        render_report(report, console)
    return 1 if report.has_broken else 0