"""TUI ESC 后无响应回归 — async hook 不能同步调 LLM 阻塞事件循环。

2026-11-21 现场：expert 模式 Reflection 的充分性判断在 aafter_model 里直接
`llm.invoke()`，压缩策略的 abefore_model 也只是同步实现包一层。provider 一慢，
Textual 事件循环整个卡住：ESC 无法处理，下一次输入也进不来（“模型不回应”）。
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from engram.backend.agents.context_engineering.contract import (
    GovernanceContext,
    GovernanceResult,
)
from engram.backend.agents.context_engineering.strategies.default.strategy import (
    DefaultStrategy,
)
from engram.backend.agents.middlewares.reflection_middleware import (
    ReflectionMiddleware,
    SufficiencyStrategy,
)


class _AsyncOnlyLLM:
    def __init__(self, content: str = '{"sufficient": true}', delay: float = 0.0) -> None:
        self.content = content
        self.delay = delay
        self.sync_calls = 0
        self.async_calls = 0

    def invoke(self, *args, **kwargs):
        self.sync_calls += 1
        raise AssertionError("async hook must not call sync llm.invoke()")

    async def ainvoke(self, messages, config=None):
        self.async_calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return AIMessage(content=self.content)


def _state() -> dict:
    return {
        "messages": [AIMessage(content="final answer", tool_calls=[])],
        "research_question": "research solid-state battery progress",
        "todos": [{"content": "collect evidence", "status": "completed"}],
        "observations": [{"step_id": "todo-0", "content": "evidence"}],
        "errors": [],
    }


def _runtime(run_id: str = "r-async") -> SimpleNamespace:
    return SimpleNamespace(context={"run_id": run_id, "thread_id": "t-async", "journal": None})


def test_async_reflection_uses_ainvoke_not_blocking_invoke(monkeypatch) -> None:
    monkeypatch.setenv("ENGRAM_INTERNAL_LLM_TIMEOUT", "5")
    llm = _AsyncOnlyLLM('{"sufficient": true}')
    mw = ReflectionMiddleware(strategy=SufficiencyStrategy(llm=llm))

    result = asyncio.run(mw.aafter_model(_state(), _runtime()))

    assert llm.sync_calls == 0
    assert llm.async_calls == 1
    assert result is None  # sufficient → pass


def test_async_reflection_times_out_instead_of_hanging(monkeypatch) -> None:
    monkeypatch.setenv("ENGRAM_INTERNAL_LLM_TIMEOUT", "0.05")
    llm = _AsyncOnlyLLM('{"sufficient": true}', delay=5.0)
    mw = ReflectionMiddleware(strategy=SufficiencyStrategy(llm=llm))

    result = asyncio.run(asyncio.wait_for(
        mw.aafter_model(_state(), _runtime("r-timeout")),
        timeout=2,
    ))

    assert llm.sync_calls == 0
    assert result is not None
    assert result["jump_to"] == "model"
    guidance = result["messages"][0].content
    assert "LLM 评估" in guidance


def test_default_strategy_async_before_model_runs_off_event_loop() -> None:
    strategy = DefaultStrategy(params={})
    seen: dict[str, str] = {}

    def fake_before_model(ctx: GovernanceContext) -> GovernanceResult:
        seen["thread"] = threading.current_thread().name
        return GovernanceResult()

    strategy.before_model = fake_before_model  # type: ignore[method-assign]
    ctx = GovernanceContext(
        state={},
        governance=None,
        config={},
        token_counter=lambda msgs: 0,
        runtime=None,
        hook="before_model",
        messages=[],
    )

    asyncio.run(strategy.abefore_model(ctx))

    assert seen["thread"] != threading.main_thread().name