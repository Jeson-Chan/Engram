"""RunProjection — chat/research 共用的运行历史 PG 投影（E2E 缺陷 G）。

E2E 现场：只有 /research 在 run 生命周期调用 PGRunStore.upsert，
/chat 完全没有 run_store 写入；断连时 mark_failed 只写本地 journal。
同一会话多次 chat + 一次真实断连后 GET /sessions/{id}/runs 返回 []。

设计（design.md 决策 7）：chat 与 research 在 start / success / failure /
client-disconnect 四个状态转移点统一 upsert 到 PGRunStore——
时间线与运行历史共用同一份事实。

用法（端点内）：
- 正常路径：await track_run(app, ctx)（阻塞 IO 挪线程池）
- 断连路径（CancelledError 分支不能 await）：track_run_sync(app, ctx)
  —— 与该分支里既有的同步 mark_failed 一致（best-effort，不抛出）。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def record_of(runtime, run_id: str) -> dict | None:
    """RunManager 内存记录 → PG upsert 形态（RunRecord.to_dict）。

    防御式读取：runtime/RunManager 缺 get_run（测试 stub）或记录缺失 → None。
    """
    if runtime is None:
        return None
    run_manager = getattr(runtime, "run_manager", None)
    get_run = getattr(run_manager, "get_run", None)
    if not callable(get_run):
        return None
    try:
        rec = get_run(run_id)
    except Exception:
        return None
    if rec is None:
        return None
    to_dict = getattr(rec, "to_dict", None)
    if not callable(to_dict):
        return None
    try:
        return to_dict()
    except Exception:
        return None


async def track_run(app, ctx, *, status_record: dict | None = None,
                    report_path: str | None = None) -> None:
    """把 RunRecord 投影进 PG（阻塞 IO 挪线程池）。未配 PG 时 no-op。

    投影是 best-effort：任何失败（无 store / 记录缺失 / PG 不可达）只
    log，不改变 run 终态、不断流（与 research 既有语义一致）。
    """
    try:
        record = status_record or record_of(getattr(app.state, "runtime", None), ctx.run_id)
        if record is None:
            return
        store = getattr(app.state, "run_store", None)
        if store is None:
            return
        await asyncio.to_thread(_upsert, store, record, report_path)
    except Exception:
        logger.exception("run projection failed (run %s)", getattr(ctx, "run_id", None))


def track_run_sync(app, ctx, reason: str | None = None) -> None:
    """断连路径的同步 best-effort 投影（CancelledError 分支不能 await）。"""
    try:
        runtime = getattr(app.state, "runtime", None)
        store = getattr(app.state, "run_store", None)
        if store is None or runtime is None:
            return
        record = record_of(runtime, getattr(ctx, "run_id", None))
        if record is None:
            return
        _upsert(store, record, None)
    except Exception:
        logger.exception("run projection (sync) failed (run %s)", getattr(ctx, "run_id", None))


def _upsert(store, record: dict, report_path: str | None) -> None:
    if report_path is None:
        store.upsert(record)
    else:
        store.upsert(record, report_path=report_path)
