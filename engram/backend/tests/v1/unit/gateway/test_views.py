"""视图模型序列化测试 — 契约稳定性（字段齐全 / 时间与枚举稳定 / 可 JSON）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engram.backend.agents.journal.events import RunEvent
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.app.gateway.views import (
    MemoryTraceView,
    MessageView,
    RunEventView,
    RuntimeStatus,
    SessionSummary,
    memory_trace_view_from,
    message_view_from,
    run_event_view_from,
    runtime_status_from_runtime,
    session_summary_from,
)


def _record(**overrides):
    base = dict(
        session_id="sess-1234abcd",
        thread_id="thread-xyz",
        user_id="alice",
        created_at="2026-11-16T10:00:00+08:00",
        metadata={"title": "记忆研究"},
    )
    base.update(overrides)
    return SimpleNamespace(status="active", **base)


class TestSessionSummary:
    def test_fields_complete_and_json(self):
        view = session_summary_from(
            _record(),
            updated_at="2026-11-16T12:00:00+08:00",
            message_count=7,
            memory_count=3,
            last_run_status="success",
        )
        assert isinstance(view, SessionSummary)
        assert view.session_id == "sess-1234abcd"
        assert view.thread_id == "thread-xyz"
        assert view.title == "记忆研究"
        assert view.user_id == "alice"
        assert view.message_count == 7
        assert view.memory_count == 3
        assert view.last_run_status == "success"
        # 可 JSON 序列化（往返稳定）
        data = json.loads(view.model_dump_json())
        assert data["session_id"] == "sess-1234abcd"
        assert data["title"] == "记忆研究"

    def test_title_fallback(self):
        view = session_summary_from(_record(metadata={}))
        assert view.title == "Session sess-123"  # 前 8 位

    def test_defaults(self):
        view = session_summary_from(_record())
        assert view.updated_at is None
        assert view.message_count == 0
        assert view.memory_count == 0
        assert view.last_run_status is None


class TestMessageView:
    def test_human_message(self):
        view = message_view_from(HumanMessage(content="你好"))
        assert isinstance(view, MessageView)
        assert view.role == "human"
        assert view.content == "你好"
        assert view.tool_calls == []

    def test_ai_message_with_tool_calls(self):
        msg = AIMessage(
            content="我来查一下",
            tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "call_1"}],
            id="msg_9",
        )
        view = message_view_from(msg)
        assert view.role == "ai"
        assert view.tool_calls == [
            {"name": "web_search", "args": {"query": "x"}, "id": "call_1"},
        ]
        assert view.msg_id == "msg_9"
        assert json.loads(view.model_dump_json())["tool_calls"][0]["name"] == "web_search"

    def test_tool_message_role(self):
        view = message_view_from(ToolMessage(content="42", tool_call_id="call_1"))
        assert view.role == "tool"
        assert view.content == "42"

    def test_created_at_missing_is_none(self):
        view = message_view_from(HumanMessage(content="x"))
        assert view.created_at is None


class TestMemoryTraceView:
    def _trace(self, **kw):
        base = dict(
            id="t1",
            content="Alice 喜欢围棋",
            type=MemoryType.EPISODIC,
            strength=0.62,
            decay_rate=0.1,
            access_count=3,
            source="worker:thread-xyz:5",
            created_at=1763000000.0,
        )
        base.update(kw)
        return MemoryTrace(**base)

    def test_fields_and_enum_stable(self):
        view = memory_trace_view_from(self._trace(), layer="hot")
        assert isinstance(view, MemoryTraceView)
        assert view.type == "episodic"  # 枚举 → value 字符串
        assert view.layer == "hot"
        assert view.forgotten is False
        assert view.strength == 0.62
        assert view.created_at is not None and view.created_at.endswith("+00:00")
        # 可 JSON：不含枚举对象
        data = json.loads(view.model_dump_json())
        assert data["type"] == "episodic"

    def test_forgotten_marker(self):
        trace = self._trace(metadata={"forgotten": True})
        view = memory_trace_view_from(trace, layer="cold")
        assert view.forgotten is True
        assert view.layer == "cold"

    def test_layer_unknown(self):
        view = memory_trace_view_from(self._trace())
        assert view.layer is None


class TestRunEventView:
    def test_fields(self):
        event = RunEvent(
            event_id="e1",
            run_id="r1",
            event_type="llm_call",
            payload={"model": "m", "tokens": 10},
            created_at="2026-11-16T10:01:00+08:00",
        )
        view = run_event_view_from(event)
        assert isinstance(view, RunEventView)
        assert view.event_type == "llm_call"
        assert view.payload == {"model": "m", "tokens": 10}
        assert view.created_at == "2026-11-16T10:01:00+08:00"
        assert json.loads(view.model_dump_json())["event_id"] == "e1"


class TestRuntimeStatus:
    def _runtime(self):
        skill_manager = SimpleNamespace(
            list_skills=lambda: [{"skill_id": "s1", "name": "find-skills"}],
        )
        mcp_manager = SimpleNamespace(
            list_servers=lambda: [{"name": "local", "tool_count": 2}],
        )
        sandbox_cfg = SimpleNamespace(use="engram...local:LocalSandboxProvider", timeout=60)
        config = SimpleNamespace(
            runtime=SimpleNamespace(expert_mode=True),
            sandbox=sandbox_cfg,
        )
        return SimpleNamespace(
            researcher_model_name="deepseek-v4.1-flash-1017",
            skill_manager=skill_manager,
            mcp_manager=mcp_manager,
            config=config,
        )

    def test_fields_and_no_secret(self):
        import os

        old = os.environ.get("ENGRAM_PROVIDER")
        os.environ["ENGRAM_PROVIDER"] = "openai"
        try:
            view = runtime_status_from_runtime(self._runtime())
        finally:
            if old is None:
                os.environ.pop("ENGRAM_PROVIDER", None)
            else:
                os.environ["ENGRAM_PROVIDER"] = old
        assert isinstance(view, RuntimeStatus)
        assert view.model == "deepseek-v4.1-flash-1017"
        assert view.provider == "openai"
        assert view.mode == "expert"
        assert view.skills[0]["skill_id"] == "s1"
        assert view.mcp[0]["name"] == "local"
        assert view.sandbox["timeout"] == 60
        dump = view.model_dump_json()
        assert "key" not in dump.lower()
        assert "secret" not in dump.lower()

    def test_empty_runtime(self):
        view = runtime_status_from_runtime(SimpleNamespace())
        assert view.model is None
        assert view.mode is None
        assert view.skills == []
        assert view.mcp == []
        assert view.sandbox == {}

    def test_broken_managers_do_not_raise(self):
        runtime = SimpleNamespace(
            skill_manager=SimpleNamespace(list_skills=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
            mcp_manager=None,
        )
        view = runtime_status_from_runtime(runtime)
        assert view.skills == []
        assert view.mcp == []


@pytest.mark.parametrize("cls", [SessionSummary, MessageView, MemoryTraceView, RunEventView, RuntimeStatus])
def test_models_are_json_serializable(cls):
    """契约红线：每个视图模型都能直接 JSON 序列化。"""
    # 各模型最小实例
    instances = {
        SessionSummary: SessionSummary(session_id="s", thread_id="t", title="x", user_id="u"),
        MessageView: MessageView(role="human", content="c"),
        MemoryTraceView: MemoryTraceView(id="t", content="c", type="episodic", strength=0.5, decay_rate=0.1, access_count=0),
        RunEventView: RunEventView(event_id="e", event_type="x"),
        RuntimeStatus: RuntimeStatus(),
    }
    assert json.loads(instances[cls].model_dump_json())
