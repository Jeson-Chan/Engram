"""对话相关 API schema（gateway /sessions/{id}/chat SSE 端点）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /sessions/{session_id}/chat 请求体。

    skill_override（web-skill-override）：会话级 skill 强制选中名单，请求级
    携带、网关无状态（与 CLI cli_state 同构）。缺省空列表 = 仅自动激活；
    未知名/禁用 skill 由 Selector 静默跳过（selector.select_for_task）。

    runtime-knobs（会话级运行参数，同样请求级携带、网关无状态）：
    - max_loop_steps：覆写当次运行的 recursion_limit 计算（缺省回落配置）
    - reasoning_effort：思考强度归一化档位（off/low/medium/high），
      按 provider 映射为原生参数；None/off = 不附加（provider 默认）
    - context_window：上下文窗口 token 覆写，驱动压缩阈值触发点
    """

    message: str = Field(min_length=1)
    skill_override: list[str] = Field(default_factory=list)
    max_loop_steps: int | None = Field(default=None, gt=0)
    reasoning_effort: Literal["off", "low", "medium", "high"] | None = None
    context_window: int | None = Field(default=None, ge=1000, le=2_000_000)
