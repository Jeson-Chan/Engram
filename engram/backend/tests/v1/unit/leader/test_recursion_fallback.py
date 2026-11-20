"""GraphRecursionError 兜底回归 — 循环上限耗尽时必须返回报告，而非抛异常。

线上症状（2026-11-20）：web_search 死循环直到 recursion_limit 耗尽，
异步入口直接抛 GraphRecursionError，用户侧表现为"不返回结果"。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from engram.backend.agents.capabilities.registry import CapabilityRegistry
from engram.backend.agents.leader.agent import LeaderAgent
from engram.backend.agents.reporting.markdown_reporter import MarkdownReporter


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class _RecursionGraph:
    """ainvoke 必抛 GraphRecursionError；aget_state 返回部分 state。"""

    def __init__(self, values: dict) -> None:
        self._values = values

    async def ainvoke(self, state, config=None):  # noqa: ANN001
        raise GraphRecursionError("Recursion limit of 10 reached")

    async def aget_state(self, config=None):  # noqa: ANN001
        return SimpleNamespace(values=self._values)


def _run_context(expert_mode: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                expert_mode=expert_mode,
                max_loop_steps=1,
                graph_node_multiplier=1,
                plan_enabled=False,
                timezone="UTC",
            ),
            reporting=SimpleNamespace(save_artifact=False),
        ),
        run_id="run-recur",
        thread_id="thread-recur",
        journal=_Journal(),
        output_dir=Path("."),
        events_path=Path("events.jsonl"),
    )


def _agent(values: dict) -> LeaderAgent:
    registry = CapabilityRegistry(
        models={},
        tools={},
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )
    return LeaderAgent(graph=_RecursionGraph(values), capability_registry=registry)


def test_recursion_error_returns_last_ai_message_with_note() -> None:
    agent = _agent({
        "messages": [AIMessage(content="partial answer")],
        "research_question": "q",
        "observations": [],
        "sources": [],
    })
    ctx = _run_context()

    result = agent.run("q", ctx)

    assert "partial answer" in result.final_report
    assert "循环上限" in result.final_report
    assert any(et == "agent.recursion_limit" for et, _ in ctx.journal.events)


def test_recursion_error_without_ai_message_renders_observations() -> None:
    agent = _agent({
        "messages": [],
        "research_question": "q",
        "observations": [{
            "observation_id": "obs-1",
            "step_id": "todo-0",
            "content": "collected finding",
            "source_refs": (),
            "created_at": "2026-11-20T00:00:00+00:00",
        }],
        "sources": [],
    })
    ctx = _run_context()

    result = agent.run("q", ctx)

    assert "collected finding" in result.final_report
    assert "循环上限" in result.final_report


def test_recursion_error_with_no_evidence_still_returns_text() -> None:
    agent = _agent({"messages": [], "research_question": "q", "observations": [], "sources": []})
    ctx = _run_context()

    result = agent.run("q", ctx)

    assert result.final_report.strip()
    assert "循环上限" in result.final_report