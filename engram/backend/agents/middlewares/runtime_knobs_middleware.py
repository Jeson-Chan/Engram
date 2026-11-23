"""RuntimeKnobsMiddleware — 按会话思考强度改写模型请求（runtime-knobs）。

wrap_model_call 从 runtime configurable 读 ``reasoning_effort``
（_get_runtime_value 通道，与 skill_override 同路）；映射非空时用
``request.override(model=request.model.bind(**kwargs))`` 按 run 注入——
不重建运行时、不动编译后的图（design D3）。

INVARIANT：
- off / 缺省 / provider 无映射 → 不改请求（原样 handler）
- bind 返回轻量 Runnable，每次模型调用都做，无缓存成本
- 映射表在 config.reasoning_effort 单点维护
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)

from engram.backend.agents.config.reasoning_effort import (
    effort_kwargs,
    provider_kind_for_model,
)
from engram.backend.agents.middlewares.run_journal_middleware import _get_runtime_value


class RuntimeKnobsMiddleware(AgentMiddleware):
    """wrap_model_call：思考强度按会话注入（其他 runtime knob 不走模型请求）。"""

    def _override_if_needed(self, request: ModelRequest) -> ModelRequest:
        level = _get_runtime_value(getattr(request, "runtime", None), "reasoning_effort")
        if not level or level == "off":
            return request
        kwargs = effort_kwargs(provider_kind_for_model(getattr(request, "model", None)), level)
        if not kwargs:
            return request
        return request.override(model=request.model.bind(**kwargs))

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._override_if_needed(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(self._override_if_needed(request))