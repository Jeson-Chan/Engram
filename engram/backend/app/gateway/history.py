"""历史消息只读端点 — GET /sessions/{session_id}/messages。

gateway-client-api / 历史消息（design.md 决策 5）：从 LangGraph
checkpointer 读取（`graph.aget_state`），序列化为 MessageView——
checkpoint 是会话状态的真实来源，不双写消息表。

- 顺序：与原始对话一致（checkpoint messages 即时间序）
- 分页：?limit=&offset=（默认 50/0，按时间正序的窗口）
- 空会话：无 checkpoint 或无消息 → 空列表（不是错误）
- 404：session 不存在；503：runtime 未就绪
- 无 PG（InMemorySaver）：进程内仍可读；重启后自然空态（明确可预期）
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query

from engram.backend.app.gateway.views import MessageView, message_view_from

logger = logging.getLogger(__name__)


def mount_history_routes(app: FastAPI) -> None:
    """历史消息端点挂载（main.create_app 内调用）。"""

    @app.get("/sessions/{session_id}/messages", response_model=list[MessageView])
    async def read_session_messages(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[MessageView]:
        record = app.state.session_registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        runtime = app.state.runtime
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        graph = getattr(getattr(runtime, "leader_agent", None), "graph", None)
        if graph is None:
            raise HTTPException(status_code=503, detail="agent graph not available")

        try:
            snapshot = await graph.aget_state(
                {"configurable": {"thread_id": record.thread_id}}
            )
        except Exception as exc:
            # checkpointer 故障（PG 断连等）→ 503 而不是 500（持久层不可用语义）
            logger.exception("read session messages failed (session %s)", session_id)
            raise HTTPException(
                status_code=503,
                detail="checkpointer unavailable",
            ) from exc

        values = getattr(snapshot, "values", None) or {}
        messages = values.get("messages", []) if isinstance(values, dict) else []
        window = messages[offset: offset + limit]
        return [message_view_from(m) for m in window]
