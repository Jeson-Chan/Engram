"""web-skill-override — skill_override 透传链 + /skills 管理端点外部行为。

- ChatRequest.skill_override：缺省空 / 携带解析 / 非字符串项拒绝
- _build_stream_config：configurable 含 skill_override（缺省空列表）
- 端到端（夹具级）：POST chat 携带 override → fake graph 捕获的 config
  configurable 含该键（middleware 消费端由 test_injection_middleware 覆盖）
- GET /skills：列表含 enabled；模块未启用 → []
- POST /skills/{id}/enabled：启停持久；未知名 404；模块未启用 503
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from engram.backend.app.gateway.chat import _build_stream_config
from engram.backend.app.gateway.main import create_app
from engram.backend.app.schemas.chat import ChatRequest


# ---------------------------------------------------------------------------
# ChatRequest schema
# ---------------------------------------------------------------------------


def test_chat_request_defaults_empty_override() -> None:
    req = ChatRequest(message="你好")
    assert req.skill_override == []


def test_chat_request_parses_override() -> None:
    req = ChatRequest(message="你好", skill_override=["find-skills"])
    assert req.skill_override == ["find-skills"]


def test_chat_request_rejects_non_string_items() -> None:
    with pytest.raises(Exception):
        ChatRequest(message="你好", skill_override=[123])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# _build_stream_config
# ---------------------------------------------------------------------------


def _fake_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-1",
        thread_id="t1",
        user_id="u1",
        journal=SimpleNamespace(),
        output_dir="out",
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                expert_mode=False, plan_enabled=True, timezone="UTC",
                max_loop_steps=4, graph_node_multiplier=3,
            )
        ),
    )


def test_stream_config_carries_override() -> None:
    config = _build_stream_config(
        SimpleNamespace(researcher_model_name="m"), _fake_ctx(),
        ChatRequest(message="q", skill_override=["find-skills"]),
    )
    assert config["configurable"]["skill_override"] == ["find-skills"]


def test_stream_config_defaults_empty_override() -> None:
    config = _build_stream_config(SimpleNamespace(researcher_model_name="m"), _fake_ctx())
    assert config["configurable"]["skill_override"] == []


# ---------------------------------------------------------------------------
# 端点级：chat 请求 override → graph config（夹具集成）
# ---------------------------------------------------------------------------


class _ConfigCapturingGraph:
    """假 graph：捕获 astream 收到的 config，供断言透传键。"""

    def __init__(self) -> None:
        self.captured: list[dict] = []

    async def astream(self, state: Any, config: Any = None, stream_mode: Any = None) -> AsyncIterator:
        self.captured.append(config)
        yield ("messages", (AIMessageChunk(content="ok"), {}))
        yield ("values", {"messages": []})


def _make_runtime(graph: _ConfigCapturingGraph, skill_manager: Any = None) -> Any:
    class _RunManager:
        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
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

        def mark_running(self, run_id): ...
        def mark_success(self, run_id): ...
        def mark_failed(self, run_id, error): ...

    class _Runtime:
        run_manager = _RunManager()
        researcher_model_name = "fake-researcher"
        leader_agent = SimpleNamespace(graph=graph)

    _Runtime.skill_manager = skill_manager  # 类体读不到闭包同名参数，类外挂
    return _Runtime()


def _post_chat(client: TestClient, body: dict) -> None:
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(f"/sessions/{sid}/chat", json=body)
    assert resp.status_code == 200


def test_chat_request_override_reaches_graph_config() -> None:
    graph = _ConfigCapturingGraph()
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(graph))) as client:
        _post_chat(client, {"message": "q", "skill_override": ["find-skills"]})
    assert graph.captured, "graph 未被调用"
    assert graph.captured[0]["configurable"]["skill_override"] == ["find-skills"]


def test_chat_request_without_override_reaches_graph_config_empty() -> None:
    graph = _ConfigCapturingGraph()
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(graph))) as client:
        _post_chat(client, {"message": "q"})
    assert graph.captured[0]["configurable"]["skill_override"] == []


# ---------------------------------------------------------------------------
# GET /skills 与 POST /skills/{id}/enabled
# ---------------------------------------------------------------------------


class _FakeSkillStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def set_enabled(self, skill_id: str, enabled: bool) -> bool:
        self.calls.append((skill_id, enabled))
        return skill_id != "unknown"


def _fake_skill_manager() -> SimpleNamespace:
    return SimpleNamespace(
        list_skills=lambda: [
            {"skill_id": "s1", "name": "find-skills", "description": "d",
             "effective_rate": 0.5, "total_selections": 2,
             "allowed_tools": [], "enabled": True},
        ],
        store=_FakeSkillStore(),
    )


def test_skills_list_returns_entries_with_enabled() -> None:
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(_ConfigCapturingGraph(), _fake_skill_manager()))) as client:
        resp = client.get("/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["skill_id"] == "s1"
    assert body[0]["enabled"] is True


def test_skills_list_without_manager_returns_empty() -> None:
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(_ConfigCapturingGraph()))) as client:
        resp = client.get("/skills")
    assert resp.status_code == 200
    assert resp.json() == []


def test_skill_enable_persists_via_store() -> None:
    mgr = _fake_skill_manager()
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(_ConfigCapturingGraph(), mgr))) as client:
        resp = client.post("/skills/s1/enabled", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json() == {"skill_id": "s1", "enabled": False}
    assert mgr.store.calls == [("s1", False)]


def test_skill_enable_unknown_id_404() -> None:
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(_ConfigCapturingGraph(), _fake_skill_manager()))) as client:
        resp = client.post("/skills/unknown/enabled", json={"enabled": True})
    assert resp.status_code == 404


def test_skill_enable_without_manager_503() -> None:
    with TestClient(create_app(runtime_factory=lambda: _make_runtime(_ConfigCapturingGraph()))) as client:
        resp = client.post("/skills/s1/enabled", json={"enabled": True})
    assert resp.status_code == 503
