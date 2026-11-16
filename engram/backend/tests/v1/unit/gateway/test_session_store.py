"""SessionStore 持久化测试 — E2E 缺陷 F（gateway-client-api / 会话持久化）。

E2E 现场：网关重启后 GET /sessions/{id} 404、GET /sessions 返回空——
SessionRegistry 纯内存，session_id → thread_id 映射没有落库。

验证：
- SqliteSessionStore save/load_all/delete 往返（含 metadata JSON）
- SessionRegistry(store) 构造时回灌：重启语义（两个 Registry 实例共享
  同一 db 文件，第二个仍能看到第一个创建的会话）
- 网关级：两个 create_app 进程共享同一 ENGRAM_GATEWAY_DB，
  重启后 GET /sessions 仍返回旧会话且可解析 thread
- WAL 模式生效；ENGRAM_GATEWAY_DB=memory 走内存实现
- store=None 保持旧行为（纯内存）
"""

from __future__ import annotations

import sqlite3

import pytest

from engram.backend.app.gateway.registry import SessionRegistry
from engram.backend.app.gateway.session_store import (
    InMemorySessionStore,
    SqliteSessionStore,
    build_default_session_store,
)


def _make_record(**overrides):
    from engram.backend.app.gateway.registry import SessionRecord

    base = dict(
        session_id="sess-1", thread_id="thread-1", user_id="alice",
        created_at="2026-11-16T10:00:00+08:00", metadata={"topic": "记忆研究"},
    )
    base.update(overrides)
    return SessionRecord(**base)


class TestSqliteSessionStore:
    def test_save_load_roundtrip(self, tmp_path):
        store = SqliteSessionStore(tmp_path / "gateway.db")
        record = _make_record(metadata={"topic": "记忆研究", "nested": {"a": 1}})
        store.save(record)

        loaded = store.load_all()
        assert len(loaded) == 1
        got = loaded[0]
        assert got.session_id == "sess-1"
        assert got.thread_id == "thread-1"
        assert got.user_id == "alice"
        assert got.metadata == {"topic": "记忆研究", "nested": {"a": 1}}

    def test_delete_removes(self, tmp_path):
        store = SqliteSessionStore(tmp_path / "gateway.db")
        store.save(_make_record())
        store.delete("sess-1")
        assert store.load_all() == []

    def test_upsert_on_conflict(self, tmp_path):
        store = SqliteSessionStore(tmp_path / "gateway.db")
        store.save(_make_record(user_id="alice"))
        store.save(_make_record(user_id="bob"))  # 同 session_id upsert
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].user_id == "bob"

    def test_wal_mode_enabled(self, tmp_path):
        db = tmp_path / "gateway.db"
        store = SqliteSessionStore(db)
        store.save(_make_record())
        store.close()
        # WAL 是库级持久属性（journal_mode 落盘）
        conn = sqlite3.connect(str(db))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_parent_dirs_created(self, tmp_path):
        store = SqliteSessionStore(tmp_path / "deep" / "nest" / "gateway.db")
        store.save(_make_record())
        assert (tmp_path / "deep" / "nest" / "gateway.db").exists()

    def test_corrupt_metadata_json_tolerated(self, tmp_path):
        store = SqliteSessionStore(tmp_path / "gateway.db")
        with store._conn:
            store._conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                ("sess-x", "thread-x", "u", "t", "active", "{not json"),
            )
        loaded = store.load_all()
        assert loaded[0].metadata == {}  # 坏 JSON → 空 dict，不抛


class TestRegistryPersistence:
    def test_registry_reload_sees_prior_sessions(self, tmp_path):
        """重启语义：第二个 Registry（同 db）回灌第一个的会话。"""
        db = tmp_path / "gateway.db"
        first = SessionRegistry(store=SqliteSessionStore(db))
        record = first.create(user_id="alice", metadata={"topic": "demo"})

        second = SessionRegistry(store=SqliteSessionStore(db))
        assert second.get(record.session_id) is not None
        assert second.get(record.session_id).thread_id == record.thread_id
        assert len(second.list()) == 1

    def test_registry_delete_persists(self, tmp_path):
        db = tmp_path / "gateway.db"
        first = SessionRegistry(store=SqliteSessionStore(db))
        record = first.create()
        first.delete(record.session_id)

        second = SessionRegistry(store=SqliteSessionStore(db))
        assert second.get(record.session_id) is None
        assert second.list() == []

    def test_registry_without_store_keeps_legacy(self):
        registry = SessionRegistry()  # store=None：纯内存（旧行为）
        record = registry.create()
        assert registry.get(record.session_id) is record
        assert registry.delete(record.session_id) is True


class TestBuildDefaultStore:
    def test_env_path_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENGRAM_GATEWAY_DB", str(tmp_path / "custom.db"))
        store = build_default_session_store()
        assert isinstance(store, SqliteSessionStore)
        store.save(_make_record())
        assert (tmp_path / "custom.db").exists()

    def test_memory_explicit(self, monkeypatch):
        monkeypatch.setenv("ENGRAM_GATEWAY_DB", "memory")
        assert isinstance(build_default_session_store(), InMemorySessionStore)


class TestInMemoryStore:
    def test_roundtrip(self):
        store = InMemorySessionStore()
        store.save(_make_record())
        assert [r.session_id for r in store.load_all()] == ["sess-1"]
        store.delete("sess-1")
        assert store.load_all() == []


class TestGatewayRestart:
    """网关级重启：两个 create_app 共享同一 db 文件。"""

    def test_sessions_survive_gateway_restart(self, tmp_path):
        from fastapi.testclient import TestClient

        from engram.backend.app.gateway.main import create_app

        db = str(tmp_path / "gateway.db")
        # 进程 1：创建会话
        app1 = create_app(runtime_factory=lambda: object())
        app1.state.session_registry = SessionRegistry(store=SqliteSessionStore(db))
        with TestClient(app1) as client1:
            created = client1.post(
                "/sessions", json={"user_id": "alice", "metadata": {"topic": "demo"}},
            ).json()
            assert client1.get(f"/sessions/{created['session_id']}").status_code == 200

        # 进程 2（"重启"）：全新 app + registry，同一 db 文件
        app2 = create_app(runtime_factory=lambda: object())
        app2.state.session_registry = SessionRegistry(store=SqliteSessionStore(db))
        with TestClient(app2) as client2:
            listed = client2.get("/sessions").json()
            assert any(s["session_id"] == created["session_id"] for s in listed)
            # 详情仍可解析到原 thread
            detail = client2.get(f"/sessions/{created['session_id']}").json()
            assert detail["thread_id"] == created["thread_id"]
            assert detail["user_id"] == "alice"
            # 删除后 404（持久层同步）
            assert client2.delete(f"/sessions/{created['session_id']}").status_code == 204
            assert client2.get(f"/sessions/{created['session_id']}").status_code == 404
            assert client2.get("/sessions").json() == []
