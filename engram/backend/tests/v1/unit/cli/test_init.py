"""`engram init` 测试 — 显式写入、权力授予边界、旧 .env 兼容。"""
from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from engram.backend.app.cli import init_cmd
from engram.backend.app.cli.probes import ProbeResult


def _probes(
    *,
    docker: bool = True,
    pg: bool = True,
    redis: bool = True,
    node: bool = True,
    web: bool = True,
    mcp: bool = True,
    llm: bool = True,
    tavily: bool = False,
) -> dict[str, ProbeResult]:
    def result(name: str, ok: bool, detail: str = "") -> ProbeResult:
        return ProbeResult(name, ok, detail or (f"{name} ok" if ok else f"{name} missing"))

    return {
        "docker": result("docker", docker),
        "pg": result("pg", pg),
        "redis": result("redis", redis),
        "node": result("node", node),
        "web_dist": result("web_dist", web),
        "mcp_config": result("mcp_config", mcp),
        "llm": result("llm", llm),
        "tavily": result("tavily", tavily),
    }


def _input_from(values: list[str]):
    iterator = iter(values)

    def _input(_prompt: str) -> str:
        return next(iterator)

    return _input


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, width=120)


def _run(tmp_path: Path, answers: list[str], probes: dict[str, ProbeResult], **kwargs):
    return init_cmd.run_init(
        tmp_path,
        input_fn=_input_from(answers),
        console=_console(),
        probes=probes,
        **kwargs,
    )


def _env(tmp_path: Path) -> str:
    return (tmp_path / ".env").read_text(encoding="utf-8")


def test_init_writes_explicit_config(tmp_path: Path):
    probes = _probes()
    # provider 编号=1(deepseek) → key → tavily → MCP=yes → sandbox=yes → Docker 模式(回车)
    answers = ["1", "sk-test", "tvly-key", "y", "y", ""]
    assert _run(tmp_path, answers, probes) == 0

    content = _env(tmp_path)
    assert "DEEPSEEK_API_KEY=sk-test" in content
    assert "TAVILY_API_KEY=tvly-key" in content
    assert "ENGRAM_MCP_ENABLED=true" in content
    assert f"ENGRAM_SANDBOX_USE={init_cmd.DOCKER_SANDBOX}" in content
    # 探测结论显式写入
    assert "ENGRAM_MEMORY_USE=default" in content
    assert "ENGRAM_MEMORY_PHASE2_ENABLED=true" in content
    assert "ENGRAM_SKILL_ENABLED=true" in content
    assert "ENGRAM_WEB_UI_ENABLED=true" in content
    assert "ENGRAM_MULTIAGENT_ENABLED=true" in content
    assert "ENGRAM_SANDBOX_ALLOW_HOST_BASH" not in content


def test_permission_boundary_deps_present_but_not_consented(tmp_path: Path):
    # 所有依赖都可用，但用户对 MCP/沙箱都回答 no
    probes = _probes(docker=True, node=True, mcp=True)
    answers = ["", "", "", "n", "n"]  # 默认 provider、空 key、空 tavily、MCP no、sandbox no
    assert _run(tmp_path, answers, probes) == 0

    content = _env(tmp_path)
    assert "ENGRAM_MCP_ENABLED=false" in content
    assert "ENGRAM_SANDBOX_USE=\n" in content or content.rstrip().endswith("ENGRAM_SANDBOX_USE=")
    assert init_cmd.DOCKER_SANDBOX not in content
    assert init_cmd.LOCAL_SANDBOX not in content


def test_permission_boundary_consent_enables(tmp_path: Path):
    probes = _probes(docker=True, node=True, mcp=True)
    answers = ["", "", "", "y", "y", "1"]  # Local 沙箱
    assert _run(tmp_path, answers, probes) == 0
    content = _env(tmp_path)
    assert "ENGRAM_MCP_ENABLED=true" in content
    assert f"ENGRAM_SANDBOX_USE={init_cmd.LOCAL_SANDBOX}" in content
    assert "ENGRAM_SANDBOX_ALLOW_HOST_BASH=true" in content


def test_no_docker_degrades_to_lightweight(tmp_path: Path):
    probes = _probes(docker=False, pg=False, redis=False, node=False, web=False)
    answers = ["", "sk-test", "", "n", "y", "y"]  # sandbox yes → 无 docker → 确认 local
    assert _run(tmp_path, answers, probes) == 0
    content = _env(tmp_path)
    assert f"ENGRAM_SANDBOX_USE={init_cmd.LOCAL_SANDBOX}" in content
    assert "ENGRAM_MEMORY_PHASE2_ENABLED=false" in content
    assert "ENGRAM_WEB_UI_ENABLED=false" in content
    # 无 Docker 时不写任何 DSN
    assert "ENGRAM_CHECKPOINT_DSN" not in content
    assert "ENGRAM_MEMORY_PG_DSN" not in content
    assert "ENGRAM_REDIS_URL" not in content


def test_existing_env_is_not_rewritten(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("SENTINEL=1\n", encoding="utf-8")

    def _explode(_prompt: str) -> str:
        raise AssertionError("interactive prompt must not run")

    code = init_cmd.run_init(
        tmp_path,
        input_fn=_explode,
        console=_console(),
        probes=_probes(),
    )
    assert code == 0
    assert env_path.read_text(encoding="utf-8") == "SENTINEL=1\n"


def test_force_backs_up_and_regenerates(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("OLD=1\n", encoding="utf-8")
    answers = ["", "sk-new", "", "n", "n"]
    assert _run(tmp_path, answers, _probes(), force=True) == 0
    assert (tmp_path / ".env.bak").read_text(encoding="utf-8") == "OLD=1\n"
    assert "DEEPSEEK_API_KEY=sk-new" in _env(tmp_path)


def test_legacy_env_variables_still_drive_runtime(monkeypatch):
    """3.4：旧变量（含 provider 路径形式的沙箱配置）升级后仍被运行时读取。"""
    from engram.backend.agents.config.loader import load_config

    monkeypatch.setenv("ENGRAM_SANDBOX_USE", init_cmd.LOCAL_SANDBOX)
    monkeypatch.setenv("ENGRAM_MEMORY_USE", "default")
    monkeypatch.setenv("ENGRAM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ENGRAM_MEMORY_PHASE2_ENABLED", "true")
    config = load_config()
    assert config.sandbox.use == init_cmd.LOCAL_SANDBOX
    assert config.memory.use == "default"
    assert config.memory.redis_url == "redis://localhost:6379/0"
    assert config.memory.phase2["enabled"] is True


def test_legacy_env_is_untouched_without_force(tmp_path: Path):
    """3.4：升级用户带着完整旧 .env 时，init 不动它。"""
    old = (
        "ENGRAM_SANDBOX_USE=engram.backend.agents.sandbox.local."
        "local_sandbox_provider:LocalSandboxProvider\n"
        "ENGRAM_MCP_ENABLED=true\n"
        "ENGRAM_REDIS_URL=redis://localhost:6379/0\n"
    )
    env_path = tmp_path / ".env"
    env_path.write_text(old, encoding="utf-8")
    assert _run(tmp_path, [], _probes()) == 0
    assert env_path.read_text(encoding="utf-8") == old