"""runtime-knobs — 请求 schema + config 透传 + 端点级捕获。

- ChatRequest 三字段：缺省 None / 合法解析 / 非法拒绝
- _build_stream_config：recursion_limit 覆写与回落、configurable 键写入
  （reasoning_effort=off 不写键）、context_window
- 端点级：POST chat 携带三旋钮 → fake graph 捕获的 config 正确
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk
from pydantic import ValidationError

from engram.backend.app.gateway.chat import _build_stream_config
from engram.backend.app.gateway.main import create_app
from engram.backend.app.schemas.chat import ChatRequest


# ---------------------------------------------------------------------------
# ChatRequest schema
# ---------------------------------------------------------------------------


def test_defaults_are_none() -> None:
    req = ChatRequest(message="q")
    assert req.max_loop_steps is None
    assert req.reasoning_effort is None
    assert req.context_window is None


def test_valid_knobs_parse() -> None:
    req = ChatRequest(message="q", max_loop_steps=10, reasoning_effort="low", context_window=32_000)
    assert (req.max_loop_steps, req.reasoning_effort, req.context_window) == (10, "low", 32_000)


@pytest.mark.parametrize("bad", [
    {"max_loop_steps": 0},
    {"max_loop_steps": -3},
    {"reasoning_effort": "extreme"},
    {"context_window": 999},
    {"context_window": 2_000_001},
])
def test_invalid_knobs_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="q", **bad)


# ---------------------------------------------------------------------------
# _build_stream_config
# ---------------------------------------------------------------------------


def _fake_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-1", thread_id="t1", user_id="u1",
        journal=SimpleNamespace(), output_dir="out",
        config=SimpleNamespace(runtime=SimpleNamespace(
            expert_mode=False, plan_enabled=True, timezone="UTC",
            max_loop_steps=4, graph_node_multiplier=3,
        )),
    )


def _cfg(request: ChatRequest | None) -> dict:
    return _build_stream_config(SimpleNamespace(researcher_model_name="m"), _fake_ctx(), request)


def test_recursion_limit_override() -> None:
    cfg = _cfg(ChatRequest(message="q", max_loop_steps=10))
    assert cfg["recursion_limit"] == 10 * 3


def test_recursion_limit_default() -> None:
    cfg = _cfg(ChatRequest(message="q"))
    assert cfg["recursion_limit"] == 4 * 3
    assert _cfg(None)["recursion_limit"] == 4 * 3


def test_effort_and_window_written() -> None:
    cfg = _cfg(ChatRequest(message="q", reasoning_effort="high", context_window=64_000))
    assert cfg["configurable"]["reasoning_effort"] == "high"
    assert cfg["configurable"]["context_window"] == 64_000


def test_off_effort_not_written() -> None:
    cfg = _cfg(ChatRequest(message="q", reasoning_effort="off"))
    assert "reasoning_effort" not in cfg["configurable"]


def test_defaults_keys_absent() -> None:
    cfg = _cfg(ChatRequest(message="q"))
    assert "reasoning_effort" not in cfg["configurable"]
    assert "context_window" not in cfg["configurable"]


# ---------------------------------------------------------------------------
# 端点级：三旋钮 → graph config
# ---------------------------------------------------------------------------


class _ConfigCapturingGraph:
    def __init__(self) -> None:
        self.captured: list[dict] = []

    async def astream(self, state: Any, config: Any = None, stream_mode: Any = None) -> AsyncIterator:
        self.captured.append(config)
        yield ("messages", (AIMessageChunk(content="ok"), {}))
        yield ("values", {"messages": []})


def _make_runtime(graph: _ConfigCapturingGraph) -> Any:
    class _RunManager:
        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
            return SimpleNamespace(
                run_id="run-test-1", thread_id=thread_id, user_id=user_id,
                journal=SimpleNamespace(), output_dir="unused",
                config=SimpleNamespace(runtime=SimpleNamespace(
                    expert_mode=False, plan_enabled=True, timezone="UTC",
                    max_loop_steps=4, graph_node_multiplier=3,
                )),
            )

        def mark_running(self, run_id): ...
        def mark_success(self, run_id): ...
        def mark_failed(self, run_id, error): ...

    class _Runtime:
        run_manager = _RunManager()
        researcher_model_name = "fake-researcher"
        leader_agent = SimpleNamespace(graph=graph)

    return _Runtime()


def test_chat_request_knobs_reach_graph_config() -> None:
    graph = _ConfigCapturingGraph()
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(graph))) as client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={
            "message": "q", "max_loop_steps": 8,
            "reasoning_effort": "medium", "context_window": 16_000,
        })
    assert resp.status_code == 200
    cfg = graph.captured[0]
    assert cfg["recursion_limit"] == 8 * 3
    assert cfg["configurable"]["reasoning_effort"] == "medium"
    assert cfg["configurable"]["context_window"] == 16_000


def test_chat_request_invalid_knob_422() -> None:
    graph = _ConfigCapturingGraph()
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(graph))) as client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "q", "max_loop_steps": 0})
    assert resp.status_code == 422
    assert graph.captured == []