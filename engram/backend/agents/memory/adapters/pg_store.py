"""PostgresMemoryStore - L3 cold-tier memory on Postgres (adapters, issue 07).

Cold tier = full sediment of all traces (no TTL - it is the fallback the
hot tier evicts into). Payload stored as JSONB using the same serializer
as RedisMemoryStore (_dump/_load), so both tiers speak one format.

Schema (created idempotently on connect):
    memory_traces(trace_id PK, user_id, thread_id, payload JSONB,
                  created_at FLOAT, updated_at)
user_id/thread_id lifted into columns for partition queries + migration
bookkeeping; created_at as a column feeds list_by_filter max_age checks
without parsing payloads.

Connection: sync psycopg + ConnectionPool (manager/worker call paths are
synchronous; the gateway already offloads them via asyncio.to_thread).
Pool opened eagerly on construction.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from psycopg_pool import ConnectionPool

from engram.backend.agents.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from engram.backend.agents.memory.adapters.redis_store import _dump, _load
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.agents.memory.types import MemoryFilter

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_traces (
    trace_id  TEXT PRIMARY KEY,
    user_id   TEXT NOT NULL DEFAULT 'default',
    thread_id TEXT NOT NULL DEFAULT 'default',
    payload   JSONB NOT NULL,
    created_at FLOAT NOT NULL DEFAULT 0,
    updated_at FLOAT NOT NULL DEFAULT 0
)
"""


class PostgresMemoryStore:
    """Cold-tier memory store (MemoryStore Protocol) on Postgres."""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            open=True,
        )
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA)
        logger.info("PostgresMemoryStore ready (dsn configured)")

    def close(self) -> None:
        self._pool.close()

    # ---- protocol methods ----

    def add(self, trace: MemoryTrace) -> None:
        user_id, thread_id = self._partition_of(trace)
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_traces WHERE trace_id = %s", (trace.id,)
            ).fetchone()
            if row is not None:
                raise MemoryConflictError(
                    "trace already exists: " + trace.id,
                    old_id=trace.id, new_id=trace.id,
                )
            conn.execute(
                "INSERT INTO memory_traces"
                " (trace_id, user_id, thread_id, payload, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (trace.id, user_id, thread_id, _dump(trace),
                 trace.created_at, time.time()),
            )

    def get(self, trace_id: str) -> MemoryTrace | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM memory_traces WHERE trace_id = %s", (trace_id,)
            ).fetchone()
        if row is None:
            return None
        return _load(row[0])

    def update(self, trace: MemoryTrace) -> None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_traces WHERE trace_id = %s", (trace.id,)
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(trace.id)
            conn.execute(
                "UPDATE memory_traces SET payload = %s, updated_at = %s"
                " WHERE trace_id = %s",
                (_dump(trace), time.time(), trace.id),
            )

    def batch_update(self, traces: list[MemoryTrace]) -> None:
        with self._pool.connection() as conn:
            for trace in traces:
                row = conn.execute(
                    "SELECT 1 FROM memory_traces WHERE trace_id = %s", (trace.id,)
                ).fetchone()
                if row is None:
                    raise MemoryNotFoundError(trace.id)
                conn.execute(
                    "UPDATE memory_traces SET payload = %s, updated_at = %s"
                    " WHERE trace_id = %s",
                    (_dump(trace), time.time(), trace.id),
                )

    def remove(self, trace_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM memory_traces WHERE trace_id = %s", (trace_id,))
        # idempotent: deleting an absent row is a no-op

    def list_by_type(self, type: MemoryType) -> list[MemoryTrace]:
        return [t for t in self.list_all() if t.type == type]

    def list_by_filter(self, filter: MemoryFilter) -> list[MemoryTrace]:
        clauses: list[str] = []
        params: list[Any] = []
        if filter.type_filter is not None:
            clauses.append("payload->>'type' = %s")
            params.append(filter.type_filter.value)
        if filter.min_strength > 0.0:
            clauses.append("(payload->>'strength')::float >= %s")
            params.append(filter.min_strength)
        if filter.max_age_hours is not None:
            clauses.append("created_at >= %s")
            params.append(time.time() - filter.max_age_hours * 3600.0)
        if filter.metadata_filter:
            for key, value in filter.metadata_filter.items():
                clauses.append("payload->'metadata'->>%s = %s")
                params.extend([key, str(value)])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM memory_traces" + where, params
            ).fetchall()
        return [_load(row[0]) for row in rows]

    def list_all(self) -> list[MemoryTrace]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM memory_traces ORDER BY created_at"
            ).fetchall()
        return [_load(row[0]) for row in rows]

    def count(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT count(*) FROM memory_traces").fetchone()[0]

    # ---- internals ----

    def _partition_of(self, trace: MemoryTrace) -> tuple[str, str]:
        user_id = str(trace.metadata.get("user_id", "default"))
        thread_id = trace.metadata.get("thread_id")
        if not thread_id:
            source = trace.source or ""
            if source.startswith("worker:"):
                thread_id = source.split(":")[1]
            else:
                thread_id = "default"
        return user_id, str(thread_id)
