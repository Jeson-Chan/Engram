"""SSE 流式对话端点 — /sessions/{session_id}/chat。

直接包装 EngramStreamClient.stream 异步生成器（graph.astream 路径），
产出其规范化 StreamEvent 序列（thinking / answer / tool_start / tool_end /
done / error …），以 SSE 帧吐给客户端。

红线：绝不经由同步入口（LeaderAgent.run 内部 asyncio.run 在事件循环中
会抛 RuntimeError）；流路径上的阻塞 IO（RunJournal JSONL 追加等）一律
asyncio.to_thread 挪线程池，事件流不被卡。
"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from engram.backend.app.schemas.chat import ChatRequest


SSE_MEDIA_TYPE = "text/event-stream"


def mount_chat_routes(app: FastAPI) -> None:
    """把 chat 端点挂到网关应用（main.create_app 内调用）。"""

    def _sse_frame(event: dict) -> str:
        """StreamEvent → SSE 帧（event: type + data: JSON，空行收尾）。"""
        nl = chr(10)
        payload = json.dumps(event, ensure_ascii=False)
        return ("event: " + str(event.get("type", "unknown")) + nl
                + "data: " + payload + nl + nl)


    @app.post("/sessions/{session_id}/chat")
    def chat(session_id: str, request: ChatRequest) -> StreamingResponse:
        runtime = app.state.runtime
        registry = app.state.session_registry
        record = registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        # 每请求闭包持有 run 上下文；错误在流内以 error 事件 + done 收尾
        async def _event_stream():
            run_id: str | None = None
            try:
                # 阻塞 IO（journal 目录创建 / JSONL 追加）→ 线程池
                ctx = await asyncio.to_thread(
                    _create_run_context, runtime, record,
                )
                run_id = ctx.run_id
                await asyncio.to_thread(runtime.run_manager.mark_running, ctx.run_id)
                config = _build_stream_config(runtime, ctx)

                from engram.backend.app.services.stream_service import EngramStreamClient

                client = EngramStreamClient(
                    graph=runtime.leader_agent.graph, config=config,
                )
                async for event in client.stream(request.message):
                    yield _sse_frame(event)
                await asyncio.to_thread(
                    runtime.run_manager.mark_success, ctx.run_id,
                )
            except asyncio.CancelledError:
                # 客户端断连：best-effort 标记 failed（不 await——任务已在取消中）
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
                    except Exception:
                        pass
                # 流内错误后仍以 done 收尾，客户端统一等 done 判终止
                yield _sse_frame({"type": "done", "content": "",
                                  "tool_name": None, "tool_args": None,
                                  "tool_result": None, "msg_id": None})

        return StreamingResponse(
            _event_stream(),
            media_type=SSE_MEDIA_TYPE,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


def _create_run_context(runtime, record):
    """线程池里跑的同步 run 上下文创建（journal 落盘在这发生）。"""
    return runtime.run_manager.create_run(
        thread_id=record.thread_id,
        user_id=record.user_id,
        model_name=runtime.researcher_model_name,
    )


def _build_stream_config(runtime, ctx) -> dict:
    """graph config（与 CLI _build_stream_config 同构，网关侧不带 skill_override）。"""
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
