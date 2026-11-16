"""历史消息端点测试 — gateway-client-api / 历史消息。

验证：
- 多轮对话回放顺序正确（checkpointer values.messages 时间序）
- 分页（offset/limit 窗口）
- 空会话 → 空列表（不是错误）
- 404（session 不存在）/ 503（runtime 未就绪 / checkpointer 故障）
- MessageView 序列化：role/content/tool_calls
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engram.backend.app.gateway.main import create_app


class _FakeCheckpointerGraph:
    """aget_state 返回固定 values（按 thread_id 区分）。"""

    def __init__(self, states: dict) -> None:
        self._states = states

    async def aget_state(self, config):
        thread_id = config["configurable"]["thread_id"]
        values = self._states.get(thread_id)
        if values is None:
            return SimpleNamespace(values={})
        return SimpleNamespace(values=values)


def _make_runtime(states: dict):
    graph = _FakeCheckpointerGraph(states)

    class _Runtime:
        leader_agent = SimpleNamespace(graph=graph)
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    return _Runtime()


def _client(runtime):
    app = create_app(runtime_factory=lambda: runtime)
    return TestClient(app), app


_MESSAGES = [
    HumanMessage(content="第一问", id="m1"),
    AIMessage(content="第一答", id="m2"),
    HumanMessage(content="第二问", id="m3"),
    AIMessage(
        content="调个工具",
        tool_calls=[{"name": "bash", "args": {"command": "echo hi"}, "id": "c1"}],
        id="m4",
    ),
    ToolMessage(content="hi", tool_call_id="c1", id="m5"),
    AIMessage(content="工具结果是 hi", id="m6"),
]


def test_multi_turn_replay_in_order():
    runtime = _make_runtime({"thread-replay": {"messages": _MESSAGES}})
    client, app = _client(runtime)
    with client as c:
        c.post("/sessions", json={"user_id": "u"})
        # 找到分配 thread-replay 的会话：直接给 registry 换 record
        sid = "sess-replay"
        from engram.backend.app.gateway.registry import SessionRecord

        app.state.session_registry._sessions[sid] = SessionRecord(
            session_id=sid, thread_id="thread-replay", user_id="u",
            created_at="2026-11-16T10:00:00", metadata={},
        )
        resp = c.get(f"/sessions/{sid}/messages")

    assert resp.status_code == 200
    body = resp.json()
    assert [m["role"] for m in body] == ["human", "ai", "human", "ai", "tool", "ai"]
    assert body[0]["content"] == "第一问"
    assert body[5]["content"] == "工具结果是 hi"
    # 工具调用标识
    assert body[3]["tool_calls"] == [
        {"name": "bash", "args": {"command": "echo hi"}, "id": "c1"}
    ]
    assert body[4]["role"] == "tool"


def test_pagination_window():
    runtime = _make_runtime({"thread-page": {"messages": _MESSAGES}})
    client, app = _client(runtime)
    with client as c:
        sid = "sess-page"
        from engram.backend.app.gateway.registry import SessionRecord

        app.state.session_registry._sessions[sid] = SessionRecord(
            session_id=sid, thread_id="thread-page", user_id="u",
            created_at="2026-11-16T10:00:00", metadata={},
        )
        page1 = c.get(f"/sessions/{sid}/messages", params={"limit": 2, "offset": 0}).json()
        page2 = c.get(f"/sessions/{sid}/messages", params={"limit": 2, "offset": 2}).json()

    assert [m["content"] for m in page1] == ["第一问", "第一答"]
    assert [m["content"] for m in page2] == ["第二问", "调个工具"]


def test_empty_session_returns_empty_list():
    runtime = _make_runtime({})  # 无 checkpoint
    client, app = _client(runtime)
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        resp = c.get(f"/sessions/{sid}/messages")
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_session_404():
    runtime = _make_runtime({})
    client, _ = _client(runtime)
    with client as c:
        assert c.get("/sessions/nope/messages").status_code == 404


def test_runtime_not_ready_503():
    runtime = _make_runtime({})
    client, app = _client(runtime)
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        app.state.runtime = None  # 模拟 runtime 未就绪
        resp = c.get(f"/sessions/{sid}/messages")
    assert resp.status_code == 503
    assert "runtime" in resp.json()["detail"]


def test_runtime_ready_but_none_state():
    runtime = _make_runtime({})
    client, app = _client(runtime)
    with client as c:
        # session 存在但 thread 从未跑过 → aget_state 返回空 values
        sid = c.post("/sessions").json()["session_id"]
        resp = c.get(f"/sessions/{sid}/messages")
    assert resp.status_code == 200
    assert resp.json() == []


def test_checkpointer_failure_503():
    class _BoomGraph:
        async def aget_state(self, config):
            raise RuntimeError("pg down")

    class _Runtime:
        leader_agent = SimpleNamespace(graph=_BoomGraph())
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    client, app = _client(_Runtime())
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        resp = c.get(f"/sessions/{sid}/messages")
    assert resp.status_code == 503
    assert "checkpointer" in resp.json()["detail"]
