"""real-steer — POST /sessions/{id}/steer 端点外部行为。"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                expert_mode=False, plan_enabled=True, timezone="UTC",
                max_loop_steps=4, graph_node_multiplier=3,
            ),
            sandbox=None,
        ),
        researcher_model_name="m",
        leader_agent=SimpleNamespace(graph=SimpleNamespace()),
        skill_manager=None,
        mcp_manager=None,
    )


def _client(runtime) -> TestClient:
    return TestClient(create_app(runtime_factory=lambda: runtime))


def test_steer_404_unknown_session() -> None:
    with _client(_runtime()) as client:
        resp = client.post("/sessions/nope/steer", json={"message": "x"})
    assert resp.status_code == 404


def test_steer_409_without_active_run() -> None:
    with _client(_runtime()) as client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/steer", json={"message": "x"})
    assert resp.status_code == 409


def test_steer_200_when_stream_active() -> None:
    with _client(_runtime()) as client:
        sid = client.post("/sessions").json()["session_id"]
        # 模拟活跃流（chat 端点在 _event_stream 生命周期内同样登记）
        client.app.state.active_streams.add(sid)
        resp = client.post(f"/sessions/{sid}/steer", json={"message": "补充要求"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["thread_id"]
        # 队列里确有该插话（thread 隔离键 = 会话的 thread_id）
        from engram.backend.agents.middlewares.steer_queue import get_steer_queues

        thread_id = body["thread_id"]
        assert get_steer_queues().drain(thread_id) == ["补充要求"]


def test_steer_empty_message_422() -> None:
    with _client(_runtime()) as client:
        sid = client.post("/sessions").json()["session_id"]
        client.app.state.active_streams.add(sid)
        resp = client.post(f"/sessions/{sid}/steer", json={"message": "   "})
    assert resp.status_code == 422


def test_chat_stream_clears_queue_and_active_mark() -> None:
    """chat 流结束后：活跃标记退出 + 残留插话被清（防陈旧注入）。"""
    from engram.backend.agents.middlewares.steer_queue import get_steer_queues

    class _Graph:
        async def astream(self, state, config=None, stream_mode=None):
            yield ("messages", (SimpleNamespace(content="ok"), {}))
            yield ("values", {"messages": []})

    class _RunManager:
        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
            return SimpleNamespace(
                run_id="run-1", thread_id=thread_id, user_id=user_id,
                journal=SimpleNamespace(), output_dir="o",
                config=SimpleNamespace(runtime=SimpleNamespace(
                    expert_mode=False, plan_enabled=True, timezone="UTC",
                    max_loop_steps=4, graph_node_multiplier=3,
                )),
            )

        def mark_running(self, run_id): ...
        def mark_success(self, run_id): ...
        def mark_failed(self, run_id, error): ...

    rt = _runtime()
    rt.run_manager = _RunManager()
    rt.leader_agent = SimpleNamespace(graph=_Graph())
    with _client(rt) as client:
        sid = client.post("/sessions").json()["session_id"]
        record = client.app.state.session_registry.get(sid)
        get_steer_queues().put(record.thread_id, "残留")
        resp = client.post(f"/sessions/{sid}/chat", json={"message": "q"})
        assert resp.status_code == 200
        assert sid not in client.app.state.active_streams
        assert get_steer_queues().drain(record.thread_id) == []