"""SSE chat 端点外部行为测试 — 事件序列（顺序 / 类型 / 终止）。

Fake graph（同 stream_service 测试模式）+ stub runtime；
断言 SSE 帧格式（event: / data: JSON / 空行收尾）与 done 终止。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from engram.backend.app.gateway.main import create_app


class _FakeGraph:
    """假 graph：astream 产固定 (mode, chunk) 序列。"""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    async def astream(self, state: Any, config: Any = None, stream_mode: Any = None) -> AsyncIterator:
        for c in self._chunks:
            yield c


def _make_runtime(chunks: list) -> Any:
    """Stub runtime：fake graph + 可观测的 run_manager 调用记录。"""
    calls: list[tuple] = []

    class _RunManager:
        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
            calls.append(("create_run", thread_id))
            return SimpleNamespace(
                run_id="run-test-1",
                thread_id=thread_id,
                user_id=user_id,
                journal=SimpleNamespace(),
                output_dir="unused",
                config=SimpleNamespace(
                    runtime=SimpleNamespace(
                        expert_mode=False, plan_enabled=True, timezone="UTC",
                        max_loop_steps=4, graph_node_multiplier=3,
                    )
                ),
            )

        def mark_running(self, run_id):
            calls.append(("mark_running", run_id))

        def mark_success(self, run_id):
            calls.append(("mark_success", run_id))

        def mark_failed(self, run_id, error):
            calls.append(("mark_failed", run_id, error))

    class _Runtime:
        run_manager = _RunManager()
        researcher_model_name = "fake-researcher"
        leader_agent = SimpleNamespace(graph=_FakeGraph(chunks))

    return _Runtime(), calls


def _client(runtime) -> TestClient:
    return TestClient(create_app(runtime_factory=lambda: runtime))


def _parse_sse(text: str) -> list[dict]:
    """SSE 原文 → [(event_type, data_dict)]，按空行分帧。"""
    frames = []
    for block in text.strip().split(chr(10) + chr(10)):
        if not block.strip():
            continue
        etype = None
        data = None
        for line in block.split(chr(10)):
            if line.startswith("event: "):
                etype = line[len("event: "):]
            elif line.startswith("data: "):
                import json

                data = json.loads(line[len("data: "):])
        frames.append({"event": etype, "data": data})
    return frames


def test_chat_streams_answer_then_done() -> None:
    """事件序列：answer delta → done 终止；SSE 帧格式合法。"""
    chunks = [
        ("messages", (AIMessageChunk(content="研究"), {})),
        ("values", {"messages": []}),
    ]
    runtime, calls = _make_runtime(chunks)
    with _client(runtime) as client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "研究问题"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(resp.text)
    types = [f["event"] for f in frames]
    assert types == ["answer", "done"]  # 顺序 + 终止
    assert frames[0]["data"]["content"] == "研究"
    assert frames[-1]["data"]["type"] == "done"
    # run 生命周期：create → running → success
    assert calls[0][0] == "create_run"
    assert calls[1] == ("mark_running", "run-test-1")
    assert calls[-1] == ("mark_success", "run-test-1")


def test_chat_error_event_then_done() -> None:
    """graph 抛错 → error 事件 + done 收尾（HTTP 仍是 200，流内表达）。"""
    class _BoomGraph:
        async def astream(self, state, config=None, stream_mode=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    runtime, calls = _make_runtime([])
    runtime.leader_agent.graph = _BoomGraph()
    with _client(runtime) as client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "Q"})
    frames = _parse_sse(resp.text)
    types = [f["event"] for f in frames]
    assert types == ["error", "done"]
    # content is the sanitized exception type (no raw details leak)
    assert frames[0]["data"]["content"] == "RuntimeError"
    assert calls[-1] == ("mark_failed", "run-test-1", "boom") or (
        calls[-1][0] == "mark_failed" and "boom" in calls[-1][2]
    )


def test_chat_unknown_session_404() -> None:
    runtime, _ = _make_runtime([])
    with _client(runtime) as client:
        resp = client.post("/sessions/sess-nope/chat", json={"message": "Q"})
    assert resp.status_code == 404


def test_chat_runtime_not_ready_503() -> None:
    """未过 lifespan（runtime=None）→ 503，而非流内错误。"""
    client = TestClient(create_app(runtime_factory=lambda: None))
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(f"/sessions/{sid}/chat", json={"message": "Q"})
    assert resp.status_code == 503
