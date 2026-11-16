"""Run 事件 + 状态端点测试 — gateway-client-api / 运行事件与状态。

验证（spec 场景）：
- 读取 Run 事件：按时间排序的事件列表 + 终态（真实 RunJournal 落盘格式）
- 读取运行状态：模型/模式/能力可用情况，不含密钥
- 404：无记录无日志的 run；503：runtime 未就绪

真实持久日志：用真 RunJournal（indent=2 + 空行分条的 JSONL）落 tmp 磁盘。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from engram.backend.agents.journal.run_journal import RunJournal
from engram.backend.app.gateway.main import create_app


def _make_runtime(logs_root: Path, records: dict | None = None):
    class _RunManager:
        _records = records or {}

        def get_run(self, run_id):
            return self._records.get(run_id)

    class _Runtime:
        run_manager = _RunManager()
        researcher_model_name = "deepseek-v4.1-flash"
        config = SimpleNamespace(
            runtime=SimpleNamespace(
                logs_root=str(logs_root), expert_mode=True,
            ),
            sandbox=SimpleNamespace(use="engram...LocalSandboxProvider", timeout=60),
        )
        skill_manager = SimpleNamespace(
            list_skills=lambda: [{"skill_id": "s1", "name": "find-skills"}],
        )
        mcp_manager = SimpleNamespace(
            list_servers=lambda: [{"name": "local", "tool_count": 2}],
        )

    return _Runtime()


def _client(runtime):
    app = create_app(runtime_factory=lambda: runtime)
    return TestClient(app), app


def _write_journal(logs_root: Path, run_id: str, events: list[tuple[str, dict]]):
    journal = RunJournal(run_id=run_id, events_path=logs_root / run_id / "events.jsonl")
    for event_type, payload in events:
        journal.append(event_type, payload)
    return journal


def test_run_events_ordered_with_terminal_status(tmp_path):
    events = [
        ("run.started", {"expert_mode": False}),
        ("llm.call", {"model": "m", "tokens": 10}),
        ("tool.started", {"tool": "bash"}),
        ("tool.finished", {"tool": "bash", "ok": True}),
        ("run.finished", {"total_tokens": 42}),
    ]
    _write_journal(tmp_path, "run-ev-1", events)

    class _Rec:
        run_id = "run-ev-1"
        thread_id = "thread-1"
        status = "success"

    runtime = _make_runtime(tmp_path, records={"run-ev-1": _Rec()})
    client, _ = _client(runtime)
    with client as c:
        resp = c.get("/runs/run-ev-1/events")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run-ev-1"
    assert body["status"] == "success"
    types = [e["event_type"] for e in body["events"]]
    assert types == [t for t, _ in events]  # 按时间（文件）顺序
    assert body["events"][1]["payload"] == {"model": "m", "tokens": 10}
    assert all(e["event_id"] for e in body["events"])
    assert all(e["created_at"] for e in body["events"])


def test_run_events_pagination(tmp_path):
    _write_journal(tmp_path, "run-ev-2", [(f"e{i}", {"n": i}) for i in range(5)])
    runtime = _make_runtime(tmp_path, records={"run-ev-2": SimpleNamespace(
        run_id="run-ev-2", thread_id="t", status="success")})
    client, _ = _client(runtime)
    with client as c:
        page = c.get("/runs/run-ev-2/events", params={"limit": 2, "offset": 1}).json()
    assert [e["event_type"] for e in page["events"]] == ["e1", "e2"]


def test_run_events_thread_dir_layout(tmp_path):
    """CLI 布局：threads/<thread>/runs/<run_id>/events.jsonl 也能读。"""
    run_id = "run-ev-3"
    thread_id = "thread-x"
    path = tmp_path / "threads" / thread_id / "runs" / run_id / "events.jsonl"
    journal = RunJournal(run_id=run_id, events_path=path)
    journal.append("run.started", {})

    runtime = _make_runtime(tmp_path, records={run_id: SimpleNamespace(
        run_id=run_id, thread_id=thread_id, status="running")})
    client, _ = _client(runtime)
    with client as c:
        resp = c.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    assert resp.json()["events"][0]["event_type"] == "run.started"


def test_run_events_404_unknown(tmp_path):
    runtime = _make_runtime(tmp_path)
    client, _ = _client(runtime)
    with client as c:
        assert c.get("/runs/run-ghost/events").status_code == 404


def test_run_events_runtime_not_ready_503(tmp_path):
    runtime = _make_runtime(tmp_path)
    client, app = _client(runtime)
    with client as c:
        app.state.runtime = None
        assert c.get("/runs/run-x/events").status_code == 503
        assert c.get("/status").status_code == 503


def test_status_endpoint_shape():
    runtime = _make_runtime(Path("."))
    client, _ = _client(runtime)
    with client as c:
        resp = c.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "deepseek-v4.1-flash"
    assert body["mode"] == "expert"
    assert body["skills"] == [{"skill_id": "s1", "name": "find-skills"}]
    assert body["mcp"] == [{"name": "local", "tool_count": 2}]
    assert body["sandbox"]["timeout"] == 60
    # 红线：不含密钥明文
    lowered = resp.text.lower()
    assert "api_key" not in lowered and "secret" not in lowered and "sk-" not in lowered
