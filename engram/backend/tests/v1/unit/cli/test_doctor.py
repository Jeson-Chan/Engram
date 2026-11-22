"""`engram doctor` 测试 — 三态判定、broken 场景、JSON 输出。"""
from __future__ import annotations

import io
import json
from pathlib import Path

from rich.console import Console

from engram.backend.app.cli import doctor
from engram.backend.app.cli.init_cmd import DOCKER_SANDBOX, LOCAL_SANDBOX
from engram.backend.app.cli.probes import ProbeResult


def _probes(**overrides: bool) -> dict[str, ProbeResult]:
    names = ("docker", "pg", "redis", "node", "web_dist", "mcp_config", "llm", "tavily")
    defaults = {
        "docker": True, "pg": True, "redis": True, "node": True,
        "web_dist": True, "mcp_config": True, "llm": True, "tavily": True,
    }
    defaults.update(overrides)
    return {
        name: ProbeResult(name, ok, f"{name} {'ok' if ok else 'missing'}")
        for name, ok in defaults.items()
    }


def _set_all_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ENGRAM_MEMORY_USE", "default")
    monkeypatch.setenv("ENGRAM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ENGRAM_MEMORY_PG_DSN", "postgresql://engram:engram@localhost:5432/engram")
    monkeypatch.setenv("ENGRAM_MEMORY_PHASE2_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_SKILL_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_WEB_UI_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_MULTIAGENT_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_MCP_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_SANDBOX_USE", DOCKER_SANDBOX)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


def test_all_healthy_has_no_broken(monkeypatch, tmp_path: Path):
    _set_all_enabled(monkeypatch)
    report = doctor.build_report(tmp_path, probes=_probes())
    assert report.has_broken is False
    states = {cap.key: cap.state for cap in report.capabilities}
    assert states["llm"] == "on"
    assert states["mcp"] == "on"
    assert states["sandbox"] == "on"
    assert all(item.state in ("ok", "skipped") for item in report.connectivity)


def test_mcp_enabled_but_config_missing_is_broken(monkeypatch, tmp_path: Path):
    _set_all_enabled(monkeypatch)
    probes = _probes(mcp_config=False)
    probes["mcp_config"] = ProbeResult(
        "mcp_config", False, "缺少 MCP 配置文件（/tmp/.engram/mcp_servers.yaml）",
        "创建该文件或关闭 MCP",
    )
    report = doctor.build_report(tmp_path, probes=probes)
    mcp = next(c for c in report.capabilities if c.key == "mcp")
    assert mcp.state == "broken"
    assert "mcp_servers.yaml" in mcp.detail
    assert mcp.fix
    conn = next(c for c in report.connectivity if c.key == "mcp")
    assert conn.state == "fail"


def test_no_redis_marks_hot_tier_off_with_reason(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ENGRAM_REDIS_URL", raising=False)
    monkeypatch.delenv("ENGRAM_MEMORY_PG_DSN", raising=False)
    monkeypatch.setenv("ENGRAM_MEMORY_USE", "default")
    report = doctor.build_report(tmp_path, probes=_probes(redis=False, pg=False))
    hot = next(c for c in report.capabilities if c.key == "memory_hot")
    cold = next(c for c in report.capabilities if c.key == "memory_cold")
    llm = next(c for c in report.capabilities if c.key == "llm")
    assert hot.state == "off" and "未配置" in hot.detail
    assert cold.state == "off" and "未配置" in cold.detail
    assert llm.state == "on"
    assert report.has_broken is False


def test_phase2_without_memory_is_broken(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGRAM_MEMORY_PHASE2_ENABLED", "true")
    monkeypatch.delenv("ENGRAM_MEMORY_USE", raising=False)
    report = doctor.build_report(tmp_path, probes=_probes())
    phase2 = next(c for c in report.capabilities if c.key == "memory_phase2")
    assert phase2.state == "broken"
    assert "ENGRAM_MEMORY_USE" in phase2.fix


def test_web_ui_enabled_without_dist_is_broken(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGRAM_WEB_UI_ENABLED", "true")
    report = doctor.build_report(tmp_path, probes=_probes(web_dist=False))
    web = next(c for c in report.capabilities if c.key == "web_ui")
    assert web.state == "broken"
    assert "npm run build" in web.fix


def test_docker_sandbox_without_docker_is_broken(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGRAM_SANDBOX_USE", DOCKER_SANDBOX)
    report = doctor.build_report(tmp_path, probes=_probes(docker=False))
    sandbox = next(c for c in report.capabilities if c.key == "sandbox")
    assert sandbox.state == "broken"
    assert sandbox.fix


def test_local_sandbox_reports_host_bash(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGRAM_SANDBOX_USE", LOCAL_SANDBOX)
    monkeypatch.setenv("ENGRAM_SANDBOX_ALLOW_HOST_BASH", "true")
    report = doctor.build_report(tmp_path, probes=_probes())
    sandbox = next(c for c in report.capabilities if c.key == "sandbox")
    assert sandbox.state == "on"
    assert "宿主机 bash" in sandbox.detail


def test_run_doctor_json_and_exit_code(monkeypatch, tmp_path: Path, capsys):
    _set_all_enabled(monkeypatch)
    assert doctor.run_doctor(tmp_path, as_json=True, probes=_probes()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["capabilities"] and payload["connectivity"]

    monkeypatch.setenv("ENGRAM_MCP_ENABLED", "true")
    assert doctor.run_doctor(
        tmp_path, as_json=True, probes=_probes(mcp_config=False),
    ) == 1


def test_doctor_tier_purpose_copy(monkeypatch, tmp_path: Path):
    """1.1：热层/冷层 off 文案含用途说明（治"不知道干什么用的"）。"""
    monkeypatch.delenv("ENGRAM_REDIS_URL", raising=False)
    monkeypatch.delenv("ENGRAM_MEMORY_PG_DSN", raising=False)
    monkeypatch.setenv("ENGRAM_MEMORY_USE", "default")
    report = doctor.build_report(tmp_path, probes=_probes(redis=False, pg=False))
    hot = next(c for c in report.capabilities if c.key == "memory_hot")
    cold = next(c for c in report.capabilities if c.key == "memory_cold")
    assert "热层=读取加速" in hot.detail
    assert "Markdown 单层" in hot.detail
    assert "冷层=永久沉淀" in cold.detail


def test_tui_capability_lines_show_deployment(monkeypatch, tmp_path: Path):
    """1.2：Inspector 运行环境行两态。"""
    from engram.backend.app.tui.cockpit import capability_lines

    class _Rep:
        deployment = "docker"
        capabilities = ()
    rendered = chr(10).join(str(line) for line in capability_lines(_Rep()))
    assert "运行环境：docker 容器" in rendered

    class _Rep2:
        deployment = "venv"
        capabilities = ()
    rendered = chr(10).join(str(line) for line in capability_lines(_Rep2()))
    assert "运行环境：宿主机直跑" in rendered


def test_tui_capability_lines_consume_same_report(monkeypatch, tmp_path: Path):
    """4.3：TUI Inspector 与 CLI 消费同一份 DoctorReport，状态一致。"""
    from engram.backend.app.tui.cockpit import capability_lines

    monkeypatch.setenv("ENGRAM_MCP_ENABLED", "true")
    report = doctor.build_report(tmp_path, probes=_probes(mcp_config=False))
    rendered = "\n".join(str(line) for line in capability_lines(report))
    for cap in report.capabilities:
        assert f"{cap.label}: {cap.state}" in rendered


def test_render_report_works(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGRAM_MCP_ENABLED", "true")
    report = doctor.build_report(tmp_path, probes=_probes(mcp_config=False))
    console = Console(file=io.StringIO(), force_terminal=False, width=120)
    doctor.render_report(report, console)
    output = console.file.getvalue()
    assert "能力矩阵" in output
    assert "连通性检查" in output
    assert "broken" in output