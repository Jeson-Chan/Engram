"""环境探测器测试 — 每个探测的可用/不可用路径（mock，不触网）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from engram.backend.app.cli import probes


class _FakeConn:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.executed = False
        self.closed = False

    def execute(self, _sql: str):
        self.executed = True
        if self.fail:
            raise RuntimeError("boom")

    def close(self) -> None:
        self.closed = True


def test_probe_docker_missing_binary(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda _name: None)
    result = probes.probe_docker()
    assert result.available is False
    assert "docker" in result.detail
    assert result.fix


def test_probe_docker_available(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(
        probes.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "24.0.7\n", ""),
    )
    result = probes.probe_docker()
    assert result.available is True
    assert "24.0.7" in result.detail


def test_probe_docker_daemon_down(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(
        probes.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "cannot connect\n"),
    )
    result = probes.probe_docker()
    assert result.available is False
    assert "cannot connect" in result.detail


def test_probe_node(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda _name: "/usr/bin/node")
    monkeypatch.setattr(
        probes.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "v20.11.0\n", ""),
    )
    assert probes.probe_node().available is True
    monkeypatch.setattr(probes.shutil, "which", lambda _name: None)
    assert probes.probe_node().available is False


def test_probe_redis_ok_and_fail(monkeypatch):
    import redis

    class _Client:
        def __init__(self, ok: bool) -> None:
            self.ok = ok

        def ping(self):
            if not self.ok:
                raise ConnectionError("down")
            return True

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(
        lambda cls, url, **kw: _Client(True)
    ))
    assert probes.probe_redis("redis://localhost:6379/0").available is True

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(
        lambda cls, url, **kw: _Client(False)
    ))
    result = probes.probe_redis("redis://user:secret@localhost:6379/0")
    assert result.available is False
    assert "secret" not in result.detail


def test_probe_pg_ok_and_fail(monkeypatch):
    import psycopg

    conn = _FakeConn()
    monkeypatch.setattr(psycopg, "connect", lambda dsn, **kw: conn)
    result = probes.probe_pg("postgresql://u:p@localhost:5432/db")
    assert result.available is True
    assert conn.executed and conn.closed

    def _boom(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(psycopg, "connect", _boom)
    assert probes.probe_pg("postgresql://u:p@localhost:5432/db").available is False


def test_probe_web_dist(tmp_path: Path):
    assert probes.probe_web_dist(tmp_path).available is False
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert probes.probe_web_dist(tmp_path).available is True


def test_probe_mcp_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENGRAM_MCP_CONFIG_PATH", ".engram/mcp_servers.yaml")
    assert probes.probe_mcp_config(tmp_path).available is False
    path = tmp_path / ".engram" / "mcp_servers.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("servers:\n  demo:\n    transport: stdio\n    command: echo\n", encoding="utf-8")
    result = probes.probe_mcp_config(tmp_path)
    assert result.available is True
    assert "1 个 server" in result.detail


def test_probe_llm_requires_key(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = probes.probe_llm()
    assert result.available is False
    assert "API Key" in result.detail


def test_probe_llm_endpoint_reachable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    class _Sock:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(probes.socket, "create_connection", lambda *a, **k: _Sock())
    assert probes.probe_llm().available is True

    def _refuse(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(probes.socket, "create_connection", _refuse)
    assert probes.probe_llm().available is False


def test_probe_tavily(monkeypatch):
    class _Sock:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert probes.probe_tavily().available is False
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(probes.socket, "create_connection", lambda *a, **k: _Sock())
    assert probes.probe_tavily().available is True

def test_probe_deployment_host_and_container(monkeypatch):
    """/.dockerenv 或 ENGRAM_DOCKER=1 → docker；否则宿主机。"""

def test_probe_deployment_venv_default(monkeypatch):
    """无 /.dockerenv 且无 ENGRAM_DOCKER → 宿主机直跑（available=False）。"""
    from engram.backend.app.cli.probes import probe_deployment
    monkeypatch.delenv("ENGRAM_DOCKER", raising=False)
    result = probe_deployment()
    assert result.available is False
    assert "宿主机" in result.detail


def test_probe_deployment_docker_env(monkeypatch):
    """ENGRAM_DOCKER=1 → docker（available=True）。"""
    from engram.backend.app.cli.probes import probe_deployment
    monkeypatch.setenv("ENGRAM_DOCKER", "1")
    result = probe_deployment()
    assert result.available is True
    assert "docker" in result.detail
