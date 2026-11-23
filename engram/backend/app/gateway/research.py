"""研究流式端点 + 运行历史查询 — issue 09。

POST /sessions/{session_id}/research：SSE 吐研究流（对话端点同款
EngramStreamClient 路径；沙箱 acquire 等重阻塞调用本就发生在 graph
工具执行里，事件循环永不直接触达——网关层 async 全程；显式的阻塞
IO（journal/记录）仍 asyncio.to_thread 沙箱本体不动）。
run 生命周期各转移点把记录 upsert 进 PGRunStore（报告完成后带
report_path 产物引用）。

GET /sessions/{session_id}/runs：会话运行历史（thread_id 维度全量，
重启/多 worker 可见）。
GET /runs/{run_id}/report：单次运行的最终报告（读 report_path 产物）。
"""

from __future__ import annotations

import asyncio
import logging
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from engram.backend.app.gateway.run_projection import (
    record_of as _record_of,
    track_run as _track,
    track_run_sync,
)
from engram.backend.app.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)


def mount_research_routes(app: FastAPI) -> None:
    """研究 + 历史端点挂载（main.create_app 内调用）。"""

    def _sse_frame(event: dict) -> str:
        nl = chr(10)
        payload = json.dumps(event, ensure_ascii=False)
        return ("event: " + str(event.get("type", "unknown")) + nl
                + "data: " + payload + nl + nl)

    def _pg_runs():
        """网关的运行持久层（未配 PG 时 None——历史端点 503）。"""
        return getattr(app.state, "run_store", None)

    @app.post("/sessions/{session_id}/research")
    def research(session_id: str, request: ChatRequest) -> StreamingResponse:
        runtime = app.state.runtime
        registry = app.state.session_registry
        record = registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        async def _event_stream():
            run_id = None
            try:
                # 阻塞 IO（run 上下文 + journal 落盘）→ 线程池
                ctx = await asyncio.to_thread(
                    _create_run_context, runtime, record,
                )
                run_id = ctx.run_id
                await asyncio.to_thread(runtime.run_manager.mark_running, ctx.run_id)
                await _track(app, ctx, status_record=_record_of(runtime, run_id))
                config = _build_stream_config(runtime, ctx, request)

                from engram.backend.app.services.stream_service import EngramStreamClient

                client = EngramStreamClient(
                    graph=runtime.leader_agent.graph, config=config,
                )
                # 报告产物引用：values 终帧后从 output_dir 找报告
                answer_text: list[str] = []
                async for event in client.stream(request.message):
                    if event.get("type") == "answer":
                        answer_text.append(event.get("content", ""))
                    yield _sse_frame(event)
                await asyncio.to_thread(
                    runtime.run_manager.mark_success, ctx.run_id,
                )
                # 成功后的簿记（报告产物 + PG 投影）独立 try：失败只 log，
                # 绝不把已成功的 run 翻成 ERROR（review high）
                try:
                    report_path = await asyncio.to_thread(
                        _write_report_fallback, ctx, "".join(answer_text),
                    )
                    store = _pg_runs()
                    if store is not None:
                        await asyncio.to_thread(
                            store.upsert, _record_of(runtime, run_id),
                            report_path=report_path,
                        )
                except Exception:
                    logger.exception(
                        "post-success bookkeeping failed (run %s kept SUCCESS)",
                        run_id,
                    )
            except asyncio.CancelledError:
                if run_id is not None:
                    try:
                        runtime.run_manager.mark_failed(run_id, "client disconnected")
                        # E2E 缺陷 G：断连也进 PG 运行历史（同步 best-effort，
                        # CancelledError 分支不能 await）
                        track_run_sync(app, ctx)
                    except Exception:
                        pass
                raise
            except Exception as exc:
                # 客户端只见异常类型（防 DSN/路径/凭据泄漏），详情留服务端日志
                logger.exception("research stream failed (run %s)", run_id)
                yield _sse_frame({"type": "error", "content": type(exc).__name__,
                                  "tool_name": None, "tool_args": None,
                                  "tool_result": None, "msg_id": None})
                if run_id is not None:
                    try:
                        await asyncio.to_thread(
                            runtime.run_manager.mark_failed, run_id, str(exc),
                        )
                        await _track(app, ctx, status_record=_record_of(runtime, run_id))
                    except Exception:
                        pass
                yield _sse_frame({"type": "done", "content": "",
                                  "tool_name": None, "tool_args": None,
                                  "tool_result": None, "msg_id": None})

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/sessions/{session_id}/runs")
    def list_runs(session_id: str) -> list[dict]:
        store = _pg_runs()
        if store is None:
            raise HTTPException(status_code=503, detail="run history requires PG (ENGRAM_RUNS_PG_DSN)")
        record = app.state.session_registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.list_by_thread(record.thread_id)

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str):
        store = _pg_runs()
        if store is None:
            raise HTTPException(status_code=503, detail="run history requires PG (ENGRAM_RUNS_PG_DSN)")
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        report_path = run.get("report_path")
        if not report_path:
            raise HTTPException(status_code=404, detail="run has no report yet")
        import os

        if not os.path.isfile(report_path):
            raise HTTPException(status_code=410, detail="report artifact no longer on disk")
        return FileResponse(report_path, media_type="text/markdown")


# ---- helpers（与 chat.py 同构；共享 _create_run_context/_build_stream_config 语义） ----

def _create_run_context(runtime, record):
    return runtime.run_manager.create_run(
        thread_id=record.thread_id,
        user_id=record.user_id,
        model_name=runtime.researcher_model_name,
    )


def _build_stream_config(runtime, ctx, request: ChatRequest | None = None) -> dict:
    """graph config（与 chat.py 同构；runtime-knobs 覆写语义一致）。"""
    rc = ctx.config.runtime
    configurable: dict = {
        "expert_mode": rc.expert_mode,
        "run_id": ctx.run_id,
        "thread_id": ctx.thread_id,
        "user_id": ctx.user_id,  # E2E 缺陷 C：记忆按用户隔离
        "journal": ctx.journal,
        "output_dir": str(ctx.output_dir),
        "plan_enabled": rc.plan_enabled,
        "timezone": rc.timezone,
        "model": runtime.researcher_model_name,
        "skill_override": list(request.skill_override) if request is not None else [],
    }
    if request is not None and request.reasoning_effort and request.reasoning_effort != "off":
        configurable["reasoning_effort"] = request.reasoning_effort
    if request is not None and request.context_window is not None:
        configurable["context_window"] = request.context_window
    loop_steps = (
        request.max_loop_steps
        if request is not None and request.max_loop_steps is not None
        else rc.max_loop_steps
    )
    return {
        "configurable": configurable,
        "recursion_limit": loop_steps * rc.graph_node_multiplier,
    }


def _write_report_fallback(ctx, text: str) -> str:
    """Return this run's report artifact path; write the stream fallback only
    if no reporter artifact exists (review: prefer real artifacts).

    LeaderAgent saves final_report.md; the thread-report path saves
    report.md - check both. Only when neither exists (test stubs /
    reporter disabled) do we write the aggregated fallback, so the
    report_path reference always resolves.
    """
    import os

    artifacts_dir = str(ctx.artifacts_dir)
    os.makedirs(artifacts_dir, exist_ok=True)
    for existing in ("final_report.md", "report.md"):
        candidate = os.path.join(artifacts_dir, existing)
        if os.path.isfile(candidate):
            return candidate
    path = os.path.join(artifacts_dir, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "# (empty report)")
    return path


