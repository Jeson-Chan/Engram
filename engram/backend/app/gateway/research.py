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
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from engram.backend.app.schemas.chat import ChatRequest


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

    async def _track(ctx, status_record=None):
        """把 RunRecord 投影到 PG（阻塞 IO 挪线程池）。"""
        store = _pg_runs()
        if store is None:
            return
        record = status_record or getattr(ctx, "_record_dict", None)
        if record is None:
            return
        await asyncio.to_thread(store.upsert, record)

    def _record_of(runtime, run_id):
        rec = runtime.run_manager.get_run(run_id)
        return rec.to_dict() if rec is not None else None

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
                await _track(ctx, _record_of(runtime, run_id))
                config = _build_stream_config(runtime, ctx)

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
                # 成功后带报告引用投影（产物落盘由 reporter 在 run 内完成；
                # 网关侧把流内聚合文本存作报告 fallback）
                report_path = await asyncio.to_thread(
                    _write_report_fallback, ctx, "".join(answer_text),
                )
                store = _pg_runs()
                if store is not None:
                    await asyncio.to_thread(
                        store.upsert, _record_of(runtime, run_id),
                        report_path=report_path,
                    )
            except asyncio.CancelledError:
                if run_id is not None:
                    try:
                        runtime.run_manager.mark_failed(run_id, "client disconnected")
                    except Exception:
                        pass
                raise
            except Exception as exc:
                yield _sse_frame({"type": "error", "content": str(exc),
                                  "tool_name": None, "tool_args": None,
                                  "tool_result": None, "msg_id": None})
                if run_id is not None:
                    try:
                        await asyncio.to_thread(
                            runtime.run_manager.mark_failed, run_id, str(exc),
                        )
                        await _track(ctx, _record_of(runtime, run_id))
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


def _build_stream_config(runtime, ctx) -> dict:
    rc = ctx.config.runtime
    return {
        "configurable": {
            "expert_mode": rc.expert_mode,
            "run_id": ctx.run_id,
            "thread_id": ctx.thread_id,
            "journal": ctx.journal,
            "output_dir": str(ctx.output_dir),
            "plan_enabled": rc.plan_enabled,
            "timezone": rc.timezone,
        },
        "recursion_limit": rc.max_loop_steps * rc.graph_node_multiplier,
    }


def _write_report_fallback(ctx, text: str) -> str:
    """流内 answer 聚合的报告 fallback 落盘（reporter 产物存在时不覆盖）。

    reporter 在 run 内写的 artifact 优先；本函数保证无 artifact 场景
    （测试 stub / reporter 未启用）下 report_path 也有产物可取。
    """
    import os

    artifacts_dir = ctx.artifacts_dir
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(str(artifacts_dir), "report.md")
    existing = ctx.artifacts_dir
    # reporter 产物优先：已存在 report.md 时不覆盖
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "# (empty report)")
    return path
