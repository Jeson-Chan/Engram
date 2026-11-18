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
    """断连路径的 best-effort 投影（CancelledError 分支不能 await）。

    review medium：不能在事件循环线程上做阻塞 PG IO（慢/不可达 PG 的
    同步池获取最长等 ~30s，会卡死整个网关的所有在途流）。改为把 upsert
    调度到线程池（create_task + to_thread，不等待）；任务引用挂在 app.state
    防 GC。当前恰在事件循环内时可用；否则回退同步 best-effort（极少数
    非 loop 调用方）。
    """
    try:
        runtime = getattr(app.state, "runtime", None)
        store = getattr(app.state, "run_store", None)
        if store is None or runtime is None:
            return
        record = record_of(runtime, getattr(ctx, "run_id", None))
        if record is None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            task = loop.create_task(asyncio.to_thread(_upsert, store, record, None))
            _keep(task, app)
            return
        _upsert(store, record, None)  # 无 loop 的同步调用方（测试）
    except Exception:
        logger.exception("run projection (sync) failed (run %s)", getattr(ctx, "run_id", None))


def _keep(task: "asyncio.Task[None]", app) -> None:
    """持有 task 引用直至完成（防 GC 中断）；失败只 log。"""
    pending = getattr(app.state, "_projection_tasks", None)
    if pending is None:
        pending = set()
        app.state._projection_tasks = pending
    pending.add(task)
    task.add_done_callback(lambda t: (pending.discard(t), _log_task_error(t)))


def _log_task_error(task: "asyncio.Task[None]") -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning("run projection task failed: %s", task.exception())


def _upsert(store, record: dict, report_path: str | None) -> None:
    if report_path is None:
        store.upsert(record)
    else:
        store.upsert(record, report_path=report_path)
