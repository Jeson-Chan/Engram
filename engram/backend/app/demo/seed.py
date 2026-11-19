"""幂等演示 seed — web-tui-research-workbench 任务 7.1。

演示叙事（5 分钟）：固定 session + 预置真实记忆 + 一次 research run 与
报告——现场不依赖实时模型/外网搜索（环境限制 J/K/L 的规避，见
docs/e2e-baseline.md）。

幂等：
- 记忆：固定内容 → 固定 trace id（encode get-then-add 幂等；同用户同
  内容不重复插入）
- 会话/运行：固定 id upsert（重复执行不重复插入）
- 清理（--clean）：只删标记为 demo 的数据（固定 id），不碰其它任何
  用户数据

用法：
    python -m engram.backend.app.demo.seed           # seed（幂等）
    python -m engram.backend.app.demo.seed --clean   # 只清 demo 数据

需要 compose 起的 PG/Redis（ENGRAM_RUNS_PG_DSN / ENGRAM_MEMORY_PG_DSN /
ENGRAM_REDIS_URL / ENGRAM_MEMORY_USE=default）；缺失时给出可操作错误。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[4]

DEMO_SESSION_ID = "demo-session-0001"
DEMO_THREAD_ID = "demo-thread-0001"
DEMO_RUN_ID = "demo-run-0001"
# review high：必须与 Web/TUI 客户端的默认 user_id 一致（"default-user"）——
# 会话列表与记忆端点都按 user_id 过滤，用别的值会让 seed 数据对演示界面不可见。
DEMO_USER_ID = "default-user"

# 固定记忆内容（中文叙事：上周的 LangGraph 记忆研究）
DEMO_MEMORIES = [
    ("LangGraph 的 checkpointer 按 thread_id 隔离会话状态，PG 持久化后重启可恢复。", "semantic", 0.9),
    ("我上周研究过 Engram 的分层记忆：Redis 热层带 TTL，PG 冷层是沉淀的事实源。", "episodic", 0.8),
    ("BM25 检索分数 = similarity*0.7 + strength*0.3，衰减用 Ebbinghaus 曲线。", "semantic", 0.85),
    ("巩固（consolidate）把多条零散 episodic 合并成一条稳定 semantic，旧 trace 标记 forgotten。", "semantic", 0.88),
    ("演示当天我用 LocalSandboxProvider 验证了 bash 工具的文件读写回环。", "episodic", 0.7),
]

DEMO_REPORT = """# LangGraph 分层记忆研究（上周）

## 结论

- **会话状态**：checkpointer 按 thread_id 隔离；AsyncPostgresSaver 持久化后，
  网关重启仍可 `aget_state` 回放历史消息。
- **记忆分层**：Redis 热层（TTL + 读刷新）+ PG 冷层（全量沉淀）；
  get 先热后冷、冷命中回填热层。
- **召回**：BM25 复合分数 `similarity*0.7 + strength*0.3`，
  Ebbinghaus 衰减，forgotten 过滤在 Retriever。
- **巩固**：每 N 轮把零散 episodic 合并为 semantic，旧 trace 标记 forgotten。

## 演示要点

1. 刷新页面 → 会话与历史消息恢复（SQLite 会话映射 + checkpointer）。
2. Memory Explorer → 热层/冷层/遗忘/巩固计数与强度条。
3. 断线重连 → Last-Event-ID 补发，缺口超限显式提示。
"""


def _require_env() -> dict[str, str]:
    """演示环境前置：PG（runs + memory）+ Redis（热层）。缺失给出可操作提示。"""
    runs_dsn = os.environ.get("ENGRAM_RUNS_PG_DSN", "").strip()
    memory_dsn = os.environ.get("ENGRAM_MEMORY_PG_DSN", "").strip()
    redis_url = os.environ.get("ENGRAM_REDIS_URL", "").strip()
    missing = []
    if not runs_dsn:
        missing.append("ENGRAM_RUNS_PG_DSN")
    if not memory_dsn:
        missing.append("ENGRAM_MEMORY_PG_DSN")
    if not redis_url:
        missing.append("ENGRAM_REDIS_URL")
    if missing:
        print(
            "✗ 演示 seed 需要持久层：缺 " + ", ".join(missing) +
            "\n  先 `docker compose up -d postgres redis`，"
            "再按 .env.example 配置环境变量。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    os.environ.setdefault("ENGRAM_MEMORY_USE", "default")
    # 全局 MemoryConfig 同步（正常由 app bootstrap 做；seed 独立跑需自同步，
    # 否则 build_default_provider 读到的 redis_url 为空 → 退单层 PG store）
    from dataclasses import replace

    from engram.backend.agents.memory.config import get_memory_config, set_memory_config

    set_memory_config(replace(get_memory_config(), redis_url=redis_url))
    return {"runs": runs_dsn, "memory": memory_dsn, "redis": redis_url}


def _memory_ids() -> list[str]:
    from engram.backend.agents.memory.strategies.default.manager import (
        DefaultMemoryManager,
    )
    from engram.backend.agents.memory.schema import MemoryType

    ids = []
    for content, type_key, _importance in DEMO_MEMORIES:
        ids.append(DefaultMemoryManager._compute_trace_id(
            content, MemoryType(type_key), user_id=DEMO_USER_ID,
        ))
    return ids


def seed_memory() -> list[str]:
    """预置真实记忆（幂等：固定内容 → 固定 trace id）。返回 trace id 列表。"""
    from engram.backend.agents.memory.schema import MemoryType
    from engram.backend.agents.memory.strategies.default.strategy import (
        build_default_provider,
    )

    provider = build_default_provider()
    manager = provider.manager()
    ids: list[str] = []
    for content, type_key, importance in DEMO_MEMORIES:
        trace = manager.encode(
            content,
            MemoryType(type_key),
            importance=importance,
            source=f"seed:{DEMO_THREAD_ID}",
            metadata={
                "user_id": DEMO_USER_ID,
                "thread_id": DEMO_THREAD_ID,
                "demo": True,
            },
        )
        ids.append(trace.id)
    provider.shutdown()
    return ids


def seed_session() -> None:
    """网关会话映射（SQLite gateway.db，幂等 upsert）。"""
    from engram.backend.app.gateway.registry import SessionRecord
    from engram.backend.app.gateway.session_store import build_default_session_store

    store = build_default_session_store()
    record = SessionRecord(
        session_id=DEMO_SESSION_ID,
        thread_id=DEMO_THREAD_ID,
        user_id=DEMO_USER_ID,
        created_at="2026-11-10T09:00:00",
        metadata={"title": "上周的 LangGraph 记忆研究", "demo": True},
    )
    record.status = "active"
    store.save(record)
    if hasattr(store, "close"):
        store.close()


def seed_run(logs_root: Path) -> str:
    """一次成功 research run：PG 运行历史 + 持久事件日志 + 报告产物。

    幂等：固定 run_id upsert；journal/report 覆盖写。
    """
    from engram.backend.agents.journal.run_journal import RunJournal
    from engram.backend.agents.runtime.pg_run_store import PGRunStore

    output_dir = logs_root / DEMO_RUN_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "final_report.md"
    report_path.write_text(DEMO_REPORT, encoding="utf-8")

    # review medium：RunJournal.append 是追加模式——先清空事件文件，
    # 重复 seed 不叠加重复事件（时间线不会翻倍）
    events_path = output_dir / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    journal = RunJournal(run_id=DEMO_RUN_ID, events_path=events_path)
    for event_type, payload in [
        ("run.started", {"expert_mode": True, "demo": True}),
        ("memory.recall", {"hits": 4, "thread": DEMO_THREAD_ID}),
        ("llm.call", {"model": "seed", "tokens": 1200}),
        ("tool.started", {"tool": "bash"}),
        ("tool.finished", {"tool": "bash", "ok": True}),
        ("memory.encode", {"traces": len(DEMO_MEMORIES)}),
        ("report.generated", {"path": str(report_path)}),
        ("run.finished", {"total_tokens": 3600}),
    ]:
        journal.append(event_type, payload)

    store = PGRunStore(os.environ["ENGRAM_RUNS_PG_DSN"])
    try:
        record = {
            "run_id": DEMO_RUN_ID,
            "thread_id": DEMO_THREAD_ID,
            "user_id": DEMO_USER_ID,
            "status": "success",
            "created_at": "2026-11-10T09:05:00",
            "updated_at": "2026-11-10T09:09:00",
            "started_at": "2026-11-10T09:05:01",
            "finished_at": "2026-11-10T09:09:00",
            "model_name": "seed",
            "error": None,
            "total_tokens": 3600,
            "metadata": {"demo": True},
        }
        store.upsert(record, report_path=str(report_path))
    finally:
        store.close()
    return str(report_path)


def clean_demo() -> None:
    """只删 demo 标记的数据：固定 session / run / 记忆 / 产物目录。"""
    removed: list[str] = []

    # 同步 redis_url 到全局 MemoryConfig（同 _require_env；否则 clean 走
    # 单层 PG store，热层 trace 键残留）
    redis_url = os.environ.get("ENGRAM_REDIS_URL", "").strip()
    if redis_url:
        from dataclasses import replace

        from engram.backend.agents.memory.config import (
            get_memory_config,
            set_memory_config,
        )

        set_memory_config(replace(get_memory_config(), redis_url=redis_url))

    # 1) 会话映射（SQLite）
    from engram.backend.app.gateway.session_store import build_default_session_store

    store = build_default_session_store()
    try:
        store.delete(DEMO_SESSION_ID)
        removed.append(f"session {DEMO_SESSION_ID}")
    finally:
        if hasattr(store, "close"):
            store.close()

    # 2) 运行历史（PG runs 表）+ 产物目录
    runs_dsn = os.environ.get("ENGRAM_RUNS_PG_DSN", "").strip()
    if runs_dsn:
        from engram.backend.agents.runtime.pg_run_store import PGRunStore

        store_runs = PGRunStore(runs_dsn)
        try:
            with store_runs._pool.connection() as conn:
                conn.execute("DELETE FROM runs WHERE run_id = %s", (DEMO_RUN_ID,))
            removed.append(f"run {DEMO_RUN_ID}")
        finally:
            store_runs.close()
    logs_root = _logs_root()
    demo_dir = logs_root / DEMO_RUN_ID
    if demo_dir.exists():
        import shutil

        shutil.rmtree(demo_dir, ignore_errors=True)
        removed.append(f"artifacts {demo_dir}")

    # 3) 记忆（固定 trace id 删除——只删 demo id，不碰其它数据）
    if os.environ.get("ENGRAM_MEMORY_PG_DSN", "").strip():
        provider_store = None
        try:
            from engram.backend.agents.memory.strategies.default.strategy import (
                build_default_provider,
            )

            provider = build_default_provider()
            provider_store = provider.store()
            for trace_id in _memory_ids():
                provider_store.remove(trace_id)
                removed.append(f"memory {trace_id[:12]}…")
            provider.shutdown()
        except Exception as exc:  # noqa: BLE001
            print(f"  (memory clean skipped: {exc})")

    print("已清理 demo 数据：")
    for line in removed:
        print(f"  - {line}")


def _logs_root() -> Path:
    from engram.backend.agents.config.loader import load_config

    config = load_config()
    logs_root = Path(config.runtime.logs_root)
    if not logs_root.is_absolute():
        logs_root = _PROJECT_ROOT / logs_root
    return logs_root


def main(argv: list[str] | None = None) -> int:
    # Windows GBK 控制台打不出 ✓/✗ 等——与 cli/main.py 同款 reconfigure
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--clean" in argv:
        clean_demo()
        return 0

    _require_env()
    print("Seeding demo data (idempotent)…")
    ids = seed_memory()
    print(f"  ✓ {len(ids)} 条记忆（user={DEMO_USER_ID}, thread={DEMO_THREAD_ID}）")
    seed_session()
    print(f"  ✓ 会话 {DEMO_SESSION_ID}（SQLite gateway.db）")
    logs_root = _logs_root()
    report = seed_run(logs_root)
    print(f"  ✓ run {DEMO_RUN_ID}（PG 运行历史 + 事件日志 + 报告）")
    print(f"  ✓ 报告产物 {report}")
    print(
        "\n完成。网关启动（python -m engram.backend.app.gateway）+ ENGRAM_WEB_UI_ENABLED=true\n"
        "后：打开 /app 选择「上周的 LangGraph 记忆研究」即可开始演示；\n"
        "清理：python -m engram.backend.app.demo.seed --clean"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
