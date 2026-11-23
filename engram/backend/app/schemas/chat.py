"""对话相关 API schema（gateway /sessions/{id}/chat SSE 端点）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /sessions/{session_id}/chat 请求体。

    skill_override（web-skill-override）：会话级 skill 强制选中名单，请求级
    携带、网关无状态（与 CLI cli_state 同构）。缺省空列表 = 仅自动激活；
    未知名/禁用 skill 由 Selector 静默跳过（selector.select_for_task）。
    """

    message: str = Field(min_length=1)
    skill_override: list[str] = Field(default_factory=list)
