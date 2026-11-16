"""SessionStore — 会话映射持久层（E2E 缺陷 F / gateway-client-api）。

E2E 现场：SessionRegistry 是纯内存映射；网关重启后 GET /sessions/{id}
404、GET /sessions 空——底层 LangGraph checkpoint 确实持久化了，但客户端
拿不到 session_id → thread_id 的入口。

设计（design.md 决策 4）：默认 SQLite `.engram/gateway.db`（WAL，零运维，
单用户演示足够；多 worker 非 goal，接口预留 PG 替换）。SessionRegistry
行为不变——store 只是把 create/delete 的映射落盘，并在构造时回灌。

- `SqliteSessionStore(path)`：默认实现（ENGRAM_GATEWAY_DB 可覆盖路径）
- `InMemorySessionStore()`：测试/无磁盘环境替换实现
- store=None：SessionRegistry 纯内存（旧行为，最小兼容）

INVARIANT:
- SQLite 连接 check_same_thread=False + Lock（FastAPI 同步端点跑线程池）
- WAL：单 writer 演示语义下的并发读
- metadata 以 JSON 落盘，读回还原 dict
- 失败可见不静默：存储异常向上抛（端点 500），不吞
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from engram.backend.app.gateway.registry import SessionRecord


class SessionStore(Protocol):
    """会话映射持久层协议（SessionRegistry 的可选后端）。"""

    def save(self, record: SessionRecord) -> None: ...

    def delete(self, session_id: str) -> None: ...

    def load_all(self) -> list[SessionRecord]: ...


class InMemorySessionStore:
    """内存实现（测试 / 显式选择不落盘）。"""

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def save(self, record: SessionRecord) -> None:
        with self._lock:
            self._records[record.session_id] = record

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._records.pop(session_id, None)

    def load_all(self) -> list[SessionRecord]:
        with self._lock:
            return list(self._records.values())


class SqliteSessionStore:
    """SQLite 实现（默认 .engram/gateway.db，WAL 模式）。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        thread_id  TEXT NOT NULL,
        user_id    TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status     TEXT NOT NULL DEFAULT 'active',
        metadata   TEXT NOT NULL DEFAULT '{}'
    )
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._path), check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock, self._conn:
            self._conn.executescript(self._SCHEMA)

    def save(self, record: SessionRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions"
                " (session_id, thread_id, user_id, created_at, status, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                "   thread_id=excluded.thread_id, user_id=excluded.user_id,"
                "   created_at=excluded.created_at, status=excluded.status,"
                "   metadata=excluded.metadata",
                (
                    record.session_id, record.thread_id, record.user_id,
                    record.created_at, record.status,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )

    def delete(self, session_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )

    def load_all(self) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id, thread_id, user_id, created_at, status,"
                " metadata FROM sessions ORDER BY created_at"
            ).fetchall()
        out: list[SessionRecord] = []
        for session_id, thread_id, user_id, created_at, status, metadata_json in rows:
            record = SessionRecord(
                session_id=session_id,
                thread_id=thread_id,
                user_id=user_id,
                created_at=created_at,
                metadata=_loads(metadata_json),
            )
            record.status = status
            out.append(record)
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _loads(raw: Any) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def build_default_session_store() -> SessionStore | None:
    """生产默认：ENGRAM_GATEWAY_DB 或 .engram/gateway.db（项目根锚定）。

    显式设 ENGRAM_GATEWAY_DB=memory → 内存实现（不落盘）。
    """
    import os

    configured = os.environ.get("ENGRAM_GATEWAY_DB", "").strip()
    if configured == "memory":
        return InMemorySessionStore()
    path = configured or str(
        Path(__file__).resolve().parents[4] / ".engram" / "gateway.db"
    )
    return SqliteSessionStore(path)
