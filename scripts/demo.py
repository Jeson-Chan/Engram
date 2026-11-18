"""一键演示脚本 — web-tui-research-workbench 任务 7.2。

    python scripts/demo.py            # compose + 网关 + seed + 5 分钟脚本
    python scripts/demo.py --clean    # 只清 demo 数据

流程（干净环境可复现）：
1. docker compose up -d postgres redis
2. 等待 PG/Redis 就绪
3. 幂等 seed（固定会话/记忆/run/报告）
4. 以 Selector 兼容循环启动网关（Windows 安全，ENGRAM_WEB_UI_ENABLED=true）
5. 打印 5 分钟演示脚本（不依赖外网搜索——见 docs/e2e-baseline.md 环境限制）

Ctrl+C 结束演示（compose 容器保留现场供复查；--clean 清 demo 数据）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

PG_DSN = "postgresql://engram:engram@localhost:5432/engram"
REDIS_URL = "redis://localhost:6379/0"

# 端口可覆盖（ENGRAM_DEMO_PORT）：默认 8000 被占用/想并行起第二份时用
GATEWAY_PORT = int(os.environ.get("ENGRAM_DEMO_PORT", "8000"))
WEB_URL = f"http://127.0.0.1:{GATEWAY_PORT}/app"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, **kw)


def _wait_services(timeout: float = 60.0) -> bool:
    """轮询 PG/Redis 就绪（docker compose 起容器需要几秒）。

    review medium：探测目标必须与 seed/网关实际用的 DSN 一致（_seed_env
    优先取 ENGRAM_* env 覆盖）——否则配置指向别处时假就绪/假失败。
    """
    import psycopg
    import redis

    env = _seed_env()
    pg_dsn = env["ENGRAM_RUNS_PG_DSN"]
    redis_url = env["ENGRAM_REDIS_URL"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with psycopg.connect(pg_dsn, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            redis.Redis.from_url(redis_url, socket_connect_timeout=2).ping()
            return True
        except Exception:
            time.sleep(1.5)
    return False


def main() -> int:
    # Windows GBK 控制台打不出 ✓/╗ 等——与 cli/main.py 同款 reconfigure
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if "--clean" in sys.argv[1:]:
        env = _seed_env()
        _run([sys.executable, "-m", "engram.backend.app.demo.seed", "--clean"],
             cwd=_PROJECT_ROOT, env=env, check=False)
        return 0

    print("== 1/4 起 PG/Redis（docker compose） ==")
    up = _run(["docker", "compose", "up", "-d", "postgres", "redis"],
              cwd=_PROJECT_ROOT, check=False)
    if up.returncode != 0:
        # 同名容器已存在（跨目录 compose project 冲突）→ 直接 start 既有容器
        started = _run(["docker", "start", "engram-postgres", "engram-redis"],
                       check=False)
        if started.returncode != 0:
            print("✗ 无法启动 postgres/redis（compose 与既有容器均失败）", file=sys.stderr)
            return 2

    print("== 2/4 等待持久层就绪 ==")
    if not _wait_services():
        print("✗ PG/Redis 未在 60s 内就绪——检查 Docker Desktop 是否在运行", file=sys.stderr)
        return 2
    print("  ✓ PG + Redis 就绪")

    print("== 3/4 幂等 seed（固定会话/记忆/run/报告） ==")
    env = _seed_env()
    _run([sys.executable, "-m", "engram.backend.app.demo.seed"],
         cwd=_PROJECT_ROOT, env=env, check=True)

    print("== 4/4 启动网关（Windows Selector 安全入口 + Web UI） ==")
    gateway_env = dict(env)
    gateway_env["ENGRAM_WEB_UI_ENABLED"] = "true"
    gateway = subprocess.Popen(
        [sys.executable, "-m", "engram.backend.app.gateway",
         "--host", "127.0.0.1", "--port", str(GATEWAY_PORT)],
        cwd=_PROJECT_ROOT, env=gateway_env,
    )
    time.sleep(3)
    print(f"  ✓ 网关 PID {gateway.pid}：http://127.0.0.1:{GATEWAY_PORT}  ·  Web {WEB_URL}")

    _print_script()
    try:
        print("\n（Ctrl+C 结束演示；容器保留现场。清理 demo 数据：python scripts/demo.py --clean）")
        gateway.wait()
    except KeyboardInterrupt:
        print("\n停止网关…")
        gateway.terminate()
        try:
            gateway.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gateway.kill()
    return 0


def _seed_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "ENGRAM_RUNS_PG_DSN": env.get("ENGRAM_RUNS_PG_DSN") or PG_DSN,
        "ENGRAM_CHECKPOINT_DSN": env.get("ENGRAM_CHECKPOINT_DSN") or PG_DSN,
        "ENGRAM_MEMORY_PG_DSN": env.get("ENGRAM_MEMORY_PG_DSN") or PG_DSN,
        "ENGRAM_REDIS_URL": env.get("ENGRAM_REDIS_URL") or REDIS_URL,
        "ENGRAM_MEMORY_USE": "default",
        "ENGRAM_MEMORY_PHASE2_ENABLED": "true",
        "ENGRAM_SKILL_ENABLED": "true",
        "ENGRAM_GATEWAY_DB": str(_PROJECT_ROOT / ".engram" / "gateway.db"),
    })
    return env


def _print_script() -> None:
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  5 分钟演示脚本（{WEB_URL}）                        ║
╠══════════════════════════════════════════════════════════════╣
║ 1. 打开 Web 工作台 → 左栏选「上周的 LangGraph 记忆研究」     ║
║    （seed 预置会话：历史/记忆/run 都已就绪，无需现场生成）    ║
║ 2. Run Inspector：最近一次 run 的时间线 + 报告预览/下载       ║
║ 3. Memory Explorer：热层/冷层/遗忘/巩固计数；点筛选看强度      ║
║ 4. 现场流式研究：输入「分层记忆怎么实现？」→ 工具卡片 +      ║
║    召回提示展开（记忆按 demo-user 隔离，不会跨用户泄漏）      ║
║ 5. 断线续传：刷新页面 → 会话/历史/最近 run 恢复（SQLite +     ║
║    checkpointer）；流中途断网 → Last-Event-ID 补发            ║
║ 6. TUI 驾驶舱（另开终端 `engram`）：Ctrl+K 切会话 / Ctrl+O   ║
║    时间线 / Ctrl+G 记忆 / Ctrl+U Inspector                    ║
║ 7. （加分）清 Redis 热层 → 冷层召回仍可用；重启网关 → 会话   ║
║    仍在（记忆分层的持久性叙事）                               ║
╚══════════════════════════════════════════════════════════════╝
（叙事链路不依赖外网搜索：seed 记忆 + LocalSandbox 兜底）""")


if __name__ == "__main__":
    raise SystemExit(main())
