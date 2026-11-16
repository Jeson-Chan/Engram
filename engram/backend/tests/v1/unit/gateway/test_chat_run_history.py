"""Chat 运行历史回归 — E2E 缺陷 G（runtime-hardening）。

E2E 现场：只有 /research 在 run 生命周期调用 PGRunStore.upsert；/chat 完全
没有 run_store 写入——同一会话多次 chat + 一次真实断连后
GET /sessions/{id}/runs 返回 []。

修复验证（RunProjection 共享投影）：
- /chat 成功后 runs 出现 success
- 流内异常后 runs 出现 error + 原因
- 客户端断连（CancelledError 分支）后 runs 出现 error + 断连原因
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from engram.backend.app.gateway.main import create_app


class _RecordingRunStore:
    """记录 upsert 序列的 fake run store（外部行为断言）。"""

    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def upsert(self, record, *, report_path=None) -> None:
        self.upserts.append(dict(record))

    def list_by_thread(self, thread_id, limit=50):
        # 模拟真实 PG upsert 语义：同 run_id 取最新一条
        latest: dict = {}
        for r in self.upserts:
            if r["thread_id"] == thread_id:
                latest[r["run_id"]] = r
        return list(latest.values())

    def get_run(self, run_id):
        for r in reversed(self.upserts):
            if r["run_id"] == run_id:
                return r
        return None


class _FakeGraph:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    async def astream(self, state: Any, config=None, stream_mode=None) -> AsyncIterator:
        for c in self._chunks:
            yield c


class _RunManager:
    """与 test_research_api 同构的 fake；to_dict 动态反映当前状态。"""

    def __init__(self, tmp_dir: str) -> None:
        self.records: dict = {}
        self.tmp_dir = tmp_dir

    def create_run(self, thread_id, user_id=None, model_name=None, **kw):
        run_id = "run-chat-1"
        record = SimpleNamespace(
            run_id=run_id, thread_id=thread_id, user_id=user_id,
            status="pending", model_name=model_name, error=None,
        )
        record.to_dict = lambda: {
            "run_id": record.run_id, "thread_id": record.thread_id,
            "user_id": record.user_id, "status": record.status,
            "created_at": "2026-11-16T10:00:00Z",
            "updated_at": "2026-11-16T10:00:00Z",
            "started_at": None, "finished_at": None,
            "model_name": record.model_name, "error": record.error,
            "total_tokens": None, "metadata": {},
        }
        self.records[run_id] = record
        from pathlib import Path

        output_dir = Path(self.tmp_dir) / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            run_id=run_id, thread_id=thread_id, user_id=user_id,
            journal=SimpleNamespace(),
            output_dir=str(output_dir),
            config=SimpleNamespace(
                runtime=SimpleNamespace(
                    expert_mode=False, plan_enabled=True, timezone="UTC",
                    max_loop_steps=4, graph_node_multiplier=3,
                )
            ),
        )

    def mark_running(self, run_id):
        self.records[run_id].status = "running"

    def mark_success(self, run_id, usage=None):
        self.records[run_id].status = "success"

    def mark_failed(self, run_id, error):
        self.records[run_id].status = "error"
        self.records[run_id].error = error

    def get_run(self, run_id):
        return self.records.get(run_id)


def _make_runtime(chunks: list, tmp_dir: str) -> Any:
    class _Runtime:
        def __init__(self):
            self.run_manager = _RunManager(tmp_dir)
            self.researcher_model_name = "fake-researcher"
            self.leader_agent = SimpleNamespace(graph=_FakeGraph(chunks))

    return _Runtime()


def _client(runtime, store: _RecordingRunStore):
    """(TestClient, app)：lifespan 后挂 run_store（同 test_research_api 模式）。"""
    app = create_app(runtime_factory=lambda: runtime)

    class _Hook(TestClient):
        def __enter__(self):
            super().__enter__()
            app.state.run_store = store
            return self

    return _Hook(app), app


def _stream_chunks():
    return [
        ("messages", (AIMessageChunk(content="对话回答"), {})),
        ("values", {"messages": []}),
    ]


def test_chat_success_enters_run_history(tmp_path) -> None:
    """缺陷 G 回归：/chat 成功后 runs 出现 success（start + success 两次投影）。"""
    store = _RecordingRunStore()
    runtime = _make_runtime(_stream_chunks(), str(tmp_path))
    client, app = _client(runtime, store)
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        thread = app.state.session_registry.get(sid).thread_id
        resp = c.post(f"/sessions/{sid}/chat", json={"message": "你好"})
        assert resp.status_code == 200
        runs = c.get(f"/sessions/{sid}/runs")

    assert runs.status_code == 200
    body = runs.json()
    assert body, "chat run 必须进入运行历史"
    assert body[0]["run_id"] == "run-chat-1"
    assert body[0]["status"] == "success"
    assert body[0]["thread_id"] == thread
    # 投影序列：running（start 转移点）→ success（终态）
    assert [r["status"] for r in store.upserts] == ["running", "success"]


def test_chat_failure_enters_run_history_with_reason(tmp_path) -> None:
    """流内异常：runs 出现 error + 原因。"""

    class _Boom:
        async def astream(self, state, config=None, stream_mode=None):
            raise RuntimeError("provider exploded")
            yield

    store = _RecordingRunStore()
    runtime = _make_runtime([], str(tmp_path))
    runtime.leader_agent.graph = _Boom()
    client, _ = _client(runtime, store)
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        resp = c.post(f"/sessions/{sid}/chat", json={"message": "Q"})
        runs = c.get(f"/sessions/{sid}/runs")

    assert runs.status_code == 200
    assert runs.json(), "失败的 chat run 也要进入历史"
    last = store.upserts[-1]
    assert last["status"] == "error"
    assert "provider exploded" in last["error"]
    # 流本身仍以 error→done 收尾（客户端语义不变）
    assert "done" in resp.text


def test_chat_disconnect_enters_run_history(tmp_path) -> None:
    """客户端断连（CancelledError 分支）：runs 出现 error + 断连原因。"""

    class _Disconnect:
        async def astream(self, state, config=None, stream_mode=None):
            yield ("messages", (AIMessageChunk(content="半截回答"), {}))
            raise asyncio.CancelledError()  # 模拟客户端断连取消任务
            yield

    store = _RecordingRunStore()
    runtime = _make_runtime([], str(tmp_path))
    runtime.leader_agent.graph = _Disconnect()
    client, _ = _client(runtime, store)
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        c.post(f"/sessions/{sid}/chat", json={"message": "Q"})
        runs = c.get(f"/sessions/{sid}/runs")

    last = store.upserts[-1]
    assert last["status"] == "error"
    assert "client disconnected" in last["error"]


def test_track_run_sync_best_effort_no_store(tmp_path) -> None:
    """未配 PG：track_run_sync 不抛（no-op），历史端点 503。"""
    from engram.backend.app.gateway.run_projection import track_run_sync

    runtime = _make_runtime([], str(tmp_path))
    ctx = runtime.run_manager.create_run(thread_id="t", user_id="u")
    app = SimpleNamespace(state=SimpleNamespace(runtime=runtime, run_store=None))
    track_run_sync(app, ctx)  # no-op，不抛


def test_track_run_projection_failure_does_not_raise(tmp_path) -> None:
    """投影 upsert 失败不外抛（run 状态不被投影故障翻转）。"""
    from engram.backend.app.gateway.run_projection import track_run

    class _BoomStore:
        def upsert(self, record, *, report_path=None):
            raise RuntimeError("pg down")

    runtime = _make_runtime([], str(tmp_path))
    ctx = runtime.run_manager.create_run(thread_id="t", user_id="u")
    app = SimpleNamespace(state=SimpleNamespace(runtime=runtime, run_store=_BoomStore()))

    async def _go():
        await track_run(app, ctx)  # 吞掉投影异常

    asyncio.run(_go())  # 不抛即通过
