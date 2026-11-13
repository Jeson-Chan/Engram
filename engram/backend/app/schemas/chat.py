"""对话相关 API schema（gateway /sessions/{id}/chat SSE 端点）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /sessions/{session_id}/chat 请求体。"""

    message: str = Field(min_length=1)
