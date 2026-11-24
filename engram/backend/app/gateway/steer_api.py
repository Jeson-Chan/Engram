"""Steer 端点 — POST /sessions/{id}/steer（real-steer）。

运行活跃时把插话写入该会话 thread 的队列（SteerMiddleware 在下一模型步
注入）；无活跃运行 → 409（客户端应走正常发送路径）；会话不存在 → 404。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class SteerRequest(BaseModel):
    """POST /sessions/{id}/steer 请求体。"""

    message: str


def mount_steer_routes(app: FastAPI) -> None:
    """把 steer 端点挂到网关应用（main.create_app 内调用）。"""

    @app.post("/sessions/{session_id}/steer")
    def steer(session_id: str, payload: SteerRequest) -> dict:
        record = app.state.session_registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        runtime = app.state.runtime
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        active: set[str] = getattr(app.state, "active_streams", set())
        if session_id not in active:
            raise HTTPException(
                status_code=409,
                detail="no active run on this session; send a normal message instead",
            )

        from engram.backend.agents.middlewares.steer_queue import get_steer_queues

        accepted = get_steer_queues().put(record.thread_id, payload.message)
        if not accepted:
            raise HTTPException(status_code=422, detail="steer message must be non-empty")
        return {"accepted": True, "thread_id": record.thread_id}