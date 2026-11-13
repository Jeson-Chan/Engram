"""会话相关 API schema（gateway /sessions 端点）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    """POST /sessions 请求体。均为可选——不传即默认用户、无元数据。"""

    user_id: str = "default-user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """会话资源表示（创建/详情/列表共用）。"""

    session_id: str
    thread_id: str
    user_id: str
    created_at: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
