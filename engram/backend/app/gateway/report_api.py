"""报告生成端点 — POST /sessions/{id}/report（surface-parity）。

web 侧补齐 TUI `/report`：从指定会话的 thread 累积 state 合成报告并保存
artifact，复用渠道无关的 ``generate_report_from_thread``。同步执行
（FastAPI def 走线程池），返回 {artifact_path, final_report}。
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class ReportRequest(BaseModel):
    """POST /sessions/{id}/report 请求体（topic 可选，覆盖研究问题）。"""

    topic: str | None = None


def mount_report_routes(app: FastAPI) -> None:
    """把报告端点挂到网关应用（main.create_app 内调用）。"""

    @app.post("/sessions/{session_id}/report")
    def generate_report(session_id: str, payload: ReportRequest | None = None) -> dict:
        runtime = app.state.runtime
        record = app.state.session_registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        from pathlib import Path

        from engram.backend.agents.reporting import generate_report_from_thread

        topic = (payload.topic if payload is not None else None) or None
        # 按会话的 thread 派生报告目录（bootstrap 已锚定 logs_root 到项目根）
        logs_root = Path(runtime.config.runtime.logs_root)
        thread_dir = logs_root / "threads" / record.thread_id
        try:
            thread_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            thread_dir = runtime.thread_dir  # 兜底用活跃 thread 目录

        proxy = SimpleNamespace(
            leader_agent=runtime.leader_agent,
            thread_id=record.thread_id,
            capability_registry=runtime.capability_registry,
            thread_dir=thread_dir,
            config=runtime.config,
        )
        try:
            result = generate_report_from_thread(runtime=proxy, topic=topic)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"report generation failed: {type(exc).__name__}",
            ) from exc
        return {
            "artifact_path": result.artifact_path,
            "final_report": result.final_report,
        }