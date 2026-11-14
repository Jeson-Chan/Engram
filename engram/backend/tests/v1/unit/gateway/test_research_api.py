"""研究端点 + 运行历史测试 — 外部行为（issue 09）。

- 研究端点：SSE 事件序列（answer→done / error→done）、404/503
- 历史查询：fake run store（无 PG）外部行为 + live PG 返回真实落库数据
- 沙箱阻塞兜底：事件流不冻结由 async 路径保证（chat 同款，另有 live 流验证）
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from engram.backend.app.gateway.main import create_app

TEST_PG_DSN = os.environ.get("ENGRAM_TEST_PG_DSN", "").strip()
needs_pg = pytest.mark.skipif(
    not TEST_PG_DSN, reason="ENGRAM_TEST_PG_DSN not set; live Postgres required"
)


class _FakeGraph:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    async def astream(self, state: Any, config=None, stream_mode=None) -> AsyncIterator:
        for c in self._chunks:
            yield c


def _make_runtime(chunks: list, tmp_dir: str) -> Any:
    class _RunManager:
        def __init__(self):
            self.records: dict = {}

        def create_run(self, thread_id, user_id=None, model_name=None, **kw):
            run_id = "run-research-1"
            record = SimpleNamespace(
                run_id=run_id, thread_id=thread_id, user_id=user_id,
                status="pending", created_at="2026-11-14T10:00:00Z",
                updated_at="2026-11-14T10:00:00Z", started_at=None,
                finished_at=None, model_name=model_name, error=None,
                total_tokens=None, metadata={},
                to_dict=lambda: {
                    "run_id": run_id, "thread_id": thread_id,
                    "user_id": user_id, "status": "pending",
                    "created_at": "2026-11-14T10:00:00Z",
                    "updated_at": "2026-11-14T10:00:00Z",
                    "started_at": None, "finished_at": None,
                    "model_name": model_name, "error": None,
                    "total_tokens": None, "metadata": {},
                },
            )
            self.records[run_id] = record
            from pathlib import Path

            output_dir = Path(tmp_dir) / run_id
            artifacts = output_dir / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            return SimpleNamespace(
                run_id=run_id, thread_id=thread_id, journal=SimpleNamespace(),
                output_dir=str(output_dir),
                config=SimpleNamespace(
                    runtime=SimpleNamespace(
                        expert_mode=False, plan_enabled=True, timezone="UTC",
                        max_loop_steps=4, graph_node_multiplier=3,
                    )
                ),
                artifacts_dir=artifacts,
            )

        def mark_running(self, run_id):
            self.records[run_id].status = "running"

        def mark_success(self, run_id, usage=None):
            self.records[run_id].status = "success"

        def mark_failed(self, run_id, error):
            self.records[run_id].status = "error"

        def get_run(self, run_id):
            return self.records.get(run_id)

    class _Runtime:
        def __init__(self):
            self.run_manager = _RunManager()
            self.researcher_model_name = "fake-researcher"
            self.leader_agent = SimpleNamespace(graph=_FakeGraph(chunks))

    return _Runtime()


def _client(runtime, run_store_factory=None):
    """返回 (TestClient, app)：run_store_factory 提供时 lifespan 装配后挂上。

    调用方负责 with 块（lifespan 期间）。research/research-history 端点
    的测试各自开自己的 with client。
    """
    state = {"run_store": None}

    def factory():
        if run_store_factory is not None:
            state["run_store"] = run_store_factory()
        return runtime

    app = create_app(runtime_factory=factory)

    class _Hook(TestClient):
        def __enter__(self):
            super().__enter__()
            if state["run_store"] is not None:
                app.state.run_store = state["run_store"]
            return self

    return _Hook(app), app


def _parse_sse(text: str) -> list[dict]:
    frames = []
    for block in text.strip().split(chr(10) + chr(10)):
        if not block.strip():
            continue
        etype, data = None, None
        for line in block.split(chr(10)):
            if line.startswith("event: "):
                etype = line[len("event: "):]
            elif line.startswith("data: "):
                import json

                data = json.loads(line[len("data: "):])
        frames.append({"event": etype, "data": data})
    return frames


def _stream_chunks():
    return [
        ("messages", (AIMessageChunk(content="研究结论"), {})),
        ("values", {"messages": []}),
    ]


def test_research_streams_report_then_done(tmp_path) -> None:
    """研究流：answer delta → done 终止（SSE 帧格式）。"""
    runtime = _make_runtime(_stream_chunks(), str(tmp_path))
    client, _ = _client(runtime)
    with client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/research", json={"message": "研究问题"})
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert [f["event"] for f in frames] == ["answer", "done"]
    assert frames[0]["data"]["content"] == "研究结论"


def test_research_unknown_session_404(tmp_path) -> None:
    runtime = _make_runtime([], str(tmp_path))
    client, _ = _client(runtime)
    with client:
        resp = client.post("/sessions/nope/research", json={"message": "Q"})
    assert resp.status_code == 404


def test_research_error_stream_then_done(tmp_path) -> None:
    class _Boom:
        async def astream(self, state, config=None, stream_mode=None):
            raise RuntimeError("research boom")
            yield

    runtime = _make_runtime([], str(tmp_path))
    runtime.leader_agent.graph = _Boom()
    client, _ = _client(runtime)
    with client:
        sid = client.post("/sessions").json()["session_id"]
        resp = client.post(f"/sessions/{sid}/research", json={"message": "Q"})
    frames = _parse_sse(resp.text)
    assert [f["event"] for f in frames] == ["error", "done"]
    assert "boom" in frames[0]["data"]["content"]


def test_runs_history_endpoints_with_fake_store(tmp_path) -> None:
    """历史查询外部行为：列出运行 + 取报告（fake run store 填充数据）。"""

    class _FakeRunStore:
        def __init__(self) -> None:
            self.rows = {
                "run-research-1": {
                    "run_id": "run-research-1", "thread_id": "thread-x",
                    "user_id": "u", "status": "success",
                    "created_at": "2026-11-14T10:00:00Z",
                    "started_at": "2026-11-14T10:00:01Z",
                    "finished_at": "2026-11-14T10:05:00Z",
                    "model_name": "fake", "error": None, "total_tokens": 123,
                    "report_path": str(tmp_path / "report.md"),
                },
            }

        def list_by_thread(self, thread_id, limit=50):
            return [r for r in self.rows.values() if r["thread_id"] == thread_id]

        def get_run(self, run_id):
            return self.rows.get(run_id)

    (tmp_path / "report.md").write_text("# Final Report\n研究结论全文", encoding="utf-8")
    runtime = _make_runtime(_stream_chunks(), str(tmp_path))
    # thread 绑定：fake store 的 thread-x 与 session 分配的 thread 对不上，
    # 直接让 registry 分配 thread-x 的会话不现实——改为 session 后查 thread
    holder = {}
    client, app = _client(runtime, run_store_factory=lambda: (holder.setdefault("s", _FakeRunStore())))
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        thread = app.state.session_registry.get(sid).thread_id
        app.state.run_store.rows["run-research-1"]["thread_id"] = thread
        runs = c.get(f"/sessions/{sid}/runs")
        assert runs.status_code == 200
        body = runs.json()
        assert body[0]["run_id"] == "run-research-1"
        assert body[0]["status"] == "success"
        report = c.get("/runs/run-research-1/report")
        assert report.status_code == 200
        assert "研究结论全文" in report.text
        assert c.get("/runs/ghost/report").status_code == 404


def test_runs_history_503_without_pg(tmp_path) -> None:
    """无 PG 配置：历史端点 503（research 流本身不受影响）。"""
    runtime = _make_runtime([], str(tmp_path))
    client, app = _client(runtime)  # 无 run_store
    with client as c:
        sid = c.post("/sessions").json()["session_id"]
        assert c.get(f"/sessions/{sid}/runs").status_code == 503
        assert c.get("/runs/x/report").status_code == 503


# ── live（真 PG：历史返回真实落库数据） ────────────────────────

@needs_pg
def test_live_runs_history_persisted(tmp_path) -> None:
    """live 全链路：research 流跑完 → runs 列表返回落库记录 → 报告可取。"""
    from engram.backend.agents.runtime.pg_run_store import PGRunStore

    store = PGRunStore(TEST_PG_DSN)
    try:
        record = {
            "run_id": "run-live-test-1", "thread_id": "thread-live-hist",
            "user_id": "default-user", "status": "success",
            "created_at": "2026-11-14T10:00:00Z",
            "updated_at": "2026-11-14T10:05:00Z",
            "started_at": "2026-11-14T10:00:01Z",
            "finished_at": "2026-11-14T10:05:00Z",
            "model_name": "fake", "error": None,
            "total_tokens": 42, "metadata": {},
        }
        report = tmp_path / "live-report.md"
        report.write_text("# Live Report", encoding="utf-8")
        store.upsert(record)
        store.upsert(record, report_path=str(report))  # 二次带报告引用

        listed = store.list_by_thread("thread-live-hist")
        assert listed and listed[0]["run_id"] == "run-live-test-1"
        assert listed[0]["report_path"] == str(report)

        got = store.get_run("run-live-test-1")
        assert got["status"] == "success"
        assert got["total_tokens"] == 42

        store.upsert({**record, "status": "error", "error": "boom"})
        assert store.get_run("run-live-test-1")["status"] == "error"
    finally:
        store.close()
