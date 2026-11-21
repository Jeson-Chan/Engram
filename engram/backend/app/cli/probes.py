"""宿主机环境探测器 — 供 `engram init`（write-time 推断）与 `engram doctor` 共用。

每个探测返回可行的"可用/不可用 + 原因"，不做任何运行时副作用：
- 探测结论只由 init 写进显式 `.env`；运行时不会重新探测（D1）。
- 网络探测一律短超时（默认 1.5s），失败只返回原因，不抛。
- 详情中不打印凭据（DSN/URL 只暴露 host:port）。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_DEFAULT_PG_DSN = "postgresql://engram:engram@localhost:5432/engram"
_DEFAULT_TAVILY_HOST = ("api.tavily.com", 443)


@dataclass(frozen=True)
class ProbeResult:
    """单个探测结果。"""

    name: str
    available: bool
    detail: str
    fix: str = ""


def _host_port_from_url(url: str, default_port: int) -> tuple[str, int] | None:
    """URL → (host, port)；无法解析返回 None。"""
    try:
        parts = urlsplit(url)
        if not parts.hostname:
            return None
        return parts.hostname, parts.port or default_port
    except ValueError:
        return None


def _tcp_reachable(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} 可达"
    except OSError as exc:
        return False, f"{host}:{port} 不可达（{exc.__class__.__name__}）"


def _run_command(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def probe_docker(timeout: float = 3.0) -> ProbeResult:
    """Docker daemon 可用性（docker info 能拿到 ServerVersion）。"""
    if shutil.which("docker") is None:
        return ProbeResult("docker", False, "未找到 docker 命令", "安装 Docker Desktop/Engine")
    proc = _run_command(["docker", "info", "--format", "{{.ServerVersion}}"], timeout)
    if proc is None:
        return ProbeResult("docker", False, "docker 命令执行超时或失败", "确认 Docker daemon 已启动")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        reason = tail[-1] if tail else f"退出码 {proc.returncode}"
        return ProbeResult("docker", False, f"Docker daemon 不可用（{reason}）", "启动 Docker daemon")
    version = (proc.stdout or "").strip() or "unknown"
    return ProbeResult("docker", True, f"Docker daemon 可用（{version}）")


def probe_node(timeout: float = 2.0) -> ProbeResult:
    """Node.js 可用性（MCP stdio server / pi specialist 依赖）。"""
    if shutil.which("node") is None:
        return ProbeResult("node", False, "未找到 node 命令", "安装 Node.js 20+")
    proc = _run_command(["node", "--version"], timeout)
    if proc is None or proc.returncode != 0:
        return ProbeResult("node", False, "node --version 执行失败", "重新安装 Node.js")
    return ProbeResult("node", True, f"Node.js {(proc.stdout or '').strip()}")


def probe_redis(url: str | None = None, timeout: float = 1.5) -> ProbeResult:
    """Redis 可达性（默认 ENGRAM_REDIS_URL 或 localhost:6379）。"""
    url = url or os.environ.get("ENGRAM_REDIS_URL", "").strip() or _DEFAULT_REDIS_URL
    location = urlsplit(url)
    label = f"{location.hostname}:{location.port or 6379}"
    try:
        import redis

        client = redis.Redis.from_url(
            url, socket_connect_timeout=timeout, socket_timeout=timeout,
        )
        client.ping()
        return ProbeResult("redis", True, f"Redis 可达（{label}）")
    except Exception as exc:  # noqa: BLE001 - 探测必须绝不抛
        return ProbeResult("redis", False, f"Redis 不可达（{exc.__class__.__name__}）", "启动 Redis 或留空")


def probe_pg(dsn: str | None = None, timeout: float = 1.5) -> ProbeResult:
    """Postgres 可达性（默认探测 compose 暴露的 localhost:5432）。"""
    candidates = [
        dsn,
        os.environ.get("ENGRAM_MEMORY_PG_DSN", ""),
        os.environ.get("ENGRAM_CHECKPOINT_DSN", ""),
        _DEFAULT_PG_DSN,
    ]
    last_error = ""
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if not candidate:
            continue
        hp = _host_port_from_url(candidate, 5432)
        label = f"{hp[0]}:{hp[1]}" if hp else "Postgres"
        try:
            import psycopg

            conn = psycopg.connect(candidate, connect_timeout=timeout)
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
            return ProbeResult("pg", True, f"Postgres 可达（{label}）")
        except Exception as exc:  # noqa: BLE001
            last_error = f"{label} {exc.__class__.__name__}"
    detail = f"Postgres 不可达（{last_error}）" if last_error else "Postgres 不可达"
    return ProbeResult("pg", False, detail, "启动 Postgres 或使用 Markdown 记忆")


def probe_web_dist(project_root: Path) -> ProbeResult:
    """前端构建产物是否存在（Web 工作台依赖）。"""
    dist = project_root / "web" / "dist"
    if (dist / "index.html").is_file():
        return ProbeResult("web_dist", True, f"前端产物存在（{dist}）")
    return ProbeResult(
        "web_dist", False, "未找到 web/dist/index.html",
        "cd web && npm install && npm run build",
    )


def probe_mcp_config(project_root: Path) -> ProbeResult:
    """MCP 配置文件是否存在且可解析。"""
    raw_path = os.environ.get("ENGRAM_MCP_CONFIG_PATH", ".engram/mcp_servers.yaml")
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return ProbeResult("mcp_config", False, f"缺少 MCP 配置文件（{path}）", "创建该文件或关闭 MCP")
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("mcp_config", False, f"MCP 配置解析失败（{exc.__class__.__name__}）", "检查 YAML")
    if not isinstance(data, dict):
        return ProbeResult("mcp_config", False, "MCP 配置根节点不是 mapping", "检查 YAML")
    servers = data.get("servers") or {}
    if not servers:
        return ProbeResult(
            "mcp_config", False, "MCP 配置存在但没有可用 server",
            "在 .engram/mcp_servers.yaml 添加 servers 条目或关闭 MCP",
        )
    return ProbeResult("mcp_config", True, f"MCP 配置可用（{len(servers)} 个 server）")


def probe_llm(timeout: float = 1.5) -> ProbeResult:
    """LLM 就绪度：至少一个 provider 有密钥，且端点 TCP 可达。"""
    from engram.backend.agents.config.provider_profile import PROVIDER_PROFILES

    keyed = [
        profile for profile in PROVIDER_PROFILES
        if profile.name != "fake"
        and not profile.no_key_required
        and (os.environ.get(profile.env_key, "") or "").strip()
    ]
    keyless = [
        profile for profile in PROVIDER_PROFILES
        if profile.name != "fake" and profile.no_key_required
    ]
    if not keyed:
        # 无密钥 provider（如 Ollama）只在服务真的可达时才算"已配置"，
        # 避免装过 Ollama 但没启动时把 LLM 误报为可用。
        for profile in sorted(keyless, key=lambda p: p.priority):
            base_url = os.environ.get(profile.env_base_url, "") or profile.default_base_url or ""
            hp = _host_port_from_url(base_url, 443)
            if hp and _tcp_reachable(hp[0], hp[1], timeout)[0]:
                return ProbeResult("llm", True, f"{profile.name} 端点可达（{hp[0]}:{hp[1]}）")
        return ProbeResult(
            "llm", False, "未配置任何 LLM API Key",
            "运行 engram init 或设置 DEEPSEEK_API_KEY",
        )
    profile = sorted(keyed, key=lambda p: p.priority)[0]
    base_url = os.environ.get(profile.env_base_url, "") or profile.default_base_url or ""
    hp = _host_port_from_url(base_url, 443)
    if hp is None:
        return ProbeResult(
            "llm", False, f"{profile.name} 端点无法解析",
            f"检查 {profile.env_base_url}",
        )
    ok, detail = _tcp_reachable(hp[0], hp[1], timeout)
    if ok:
        return ProbeResult("llm", True, f"{profile.name} 端点可达（{hp[0]}:{hp[1]}）")
    return ProbeResult("llm", False, f"{profile.name} 端点不可达（{hp[0]}:{hp[1]}）", "检查网络/代理")


def probe_tavily(timeout: float = 1.5) -> ProbeResult:
    """Tavily 就绪度（可选：无 key 时搜索回退 DuckDuckGo）。"""
    key = (os.environ.get("TAVILY_API_KEY", "") or "").strip()
    if not key:
        return ProbeResult("tavily", False, "未配置 TAVILY_API_KEY（回退 DuckDuckGo）", "")
    ok, _ = _tcp_reachable(*_DEFAULT_TAVILY_HOST, timeout)
    if ok:
        return ProbeResult("tavily", True, "Tavily 端点可达")
    return ProbeResult("tavily", False, "Tavily 端点不可达", "检查网络/代理")


def probe_all(project_root: Path) -> dict[str, ProbeResult]:
    """运行全部探测（固定顺序，便于稳定输出）。"""
    results = [
        probe_docker(),
        probe_pg(),
        probe_redis(),
        probe_node(),
        probe_web_dist(project_root),
        probe_mcp_config(project_root),
        probe_llm(),
        probe_tavily(),
    ]
    return {result.name: result for result in results}