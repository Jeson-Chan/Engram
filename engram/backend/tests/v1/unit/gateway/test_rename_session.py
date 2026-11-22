"""PATCH /sessions/{id} 重命名（web-workbench-interactions 任务 1.1/1.2）。

覆盖：成功（SQLite 落盘 + 内存一致）、404 未知 id、400 空 title。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app
from engram.backend.app.gateway.registry import SessionRegistry


def _client(tmp_path: Path) -> TestClient:
    """SQLite-backed registry（真落盘路径）。"""
    from engram.backend.app.gateway.session_store import SqliteSessionStore

    registry = SessionRegistry(store=SqliteSessionStore(tmp_path / "gw.db"))
    app = create_app(runtime_factory=lambda: object())
    app.state.session_registry = registry
    return TestClient(app)


def _mk_session(client: TestClient, title: str = "旧标题") -> str:
    resp = client.post("/sessions", json={"user_id": "default-user", "title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def test_rename_success_updates_title_and_persists(tmp_path: Path):
    client = _client(tmp_path)
    sid = _mk_session(client, "旧标题")

    resp = client.patch(f"/sessions/{sid}", json={"title": "新名字"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["metadata"]["title"] == "新名字"
    assert body["session_id"] == sid

    # GET 读回：持久化生效（内存/SQLite 一致）
    got = client.get(f"/sessions/{sid}")
    assert got.status_code == 200
    assert got.json()["metadata"]["title"] == "新名字"


def test_rename_unknown_session_404(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.patch("/sessions/missing-id", json={"title": "x"})
    assert resp.status_code == 404


def test_rename_empty_title_400(tmp_path: Path):
    client = _client(tmp_path)
    sid = _mk_session(client)
    for bad in ("", "   "):
        resp = client.patch(f"/sessions/{sid}", json={"title": bad})
        assert resp.status_code == 400, f"title={bad!r}"
    # None 走 pydantic 类型校验（422）——同为"拒绝空值"语义
    resp = client.patch(f"/sessions/{sid}", json={"title": None})
    assert resp.status_code in (400, 422)


def test_registry_rename_record_consistency(tmp_path: Path):
    """registry.rename：metadata 其余键保留，未知 id 返 None。"""
    registry = SessionRegistry()
    record = registry.create(user_id="u", metadata={"title": "a", "tag": "keep"})
    updated = registry.rename(record.session_id, "b")
    assert updated is not None
    assert updated.metadata["title"] == "b"
    assert updated.metadata["tag"] == "keep"  # 其余键不动
    assert registry.rename("nope", "x") is None
