"""PGRunStore - 运行记录 Postgres 持久层（issue 09）。

运行记录从"内存 dict + 散落 JSON"（RunManager._records + record_path
散文件）落 Postgres：状态、时间线（created/started/finished）、最终
报告引用（report_path 指向 artifact markdown 落盘产物）。

RunManager 保持不动（进程内即时视图 + journal 落盘路径不变）；本层是
网关侧的持久投影——upsert on mark（chat/research 端点的状态转移点
同步写 PG），查询 API 走它（进程重启 / 多 worker 都看到全量历史）。

表（幂等建）：
    runs(run_id PK, thread_id, user_id, status, created_at, updated_at,
         started_at, finished_at, model_name, error, total_tokens,
         metadata JSONB, report_path TEXT NULL)
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    user_id      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT,
    model_name   TEXT,
    error        TEXT,
    total_tokens BIGINT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_path  TEXT
);
CREATE INDEX IF NOT EXISTS runs_thread_idx ON runs (thread_id, created_at);
"""


class PGRunStore:
    """运行记录持久层（upsert 投影 + 查询）。"""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        self._pool = ConnectionPool(
            conninfo=dsn, min_size=min_size, max_size=max_size, open=True,
        )
        with self._pool.connection() as conn:
            # psycopg execute 不支持多语句——逐条执行
            for stmt in [s2.strip() for s2 in _SCHEMA.split(chr(59)) if s2.strip()]:
                conn.execute(stmt)
        logger.info("PGRunStore ready")

    def close(self) -> None:
        self._pool.close()

    # ---- 写（upsert 投影；record 为 RunRecord.to_dict 形态） ----

    def upsert(self, record: dict[str, Any], *, report_path: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, thread_id, user_id, status, created_at,
                                  updated_at, started_at, finished_at, model_name,
                                  error, total_tokens, metadata, report_path)
                VALUES (%(run_id)s, %(thread_id)s, %(user_id)s, %(status)s,
                        %(created_at)s, %(updated_at)s, %(started_at)s,
                        %(finished_at)s, %(model_name)s, %(error)s,
                        %(total_tokens)s, %(metadata)s::jsonb,
                        COALESCE(%(report_path)s, (
                            SELECT report_path FROM runs WHERE run_id = %(run_id)s
                        )))
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    started_at = EXCLUDED.started_at,
                    finished_at = EXCLUDED.finished_at,
                    model_name = EXCLUDED.model_name,
                    error = EXCLUDED.error,
                    total_tokens = EXCLUDED.total_tokens,
                    metadata = EXCLUDED.metadata,
                    report_path = EXCLUDED.report_path
                """,
                {
                    "run_id": record["run_id"],
                    "thread_id": record["thread_id"],
                    "user_id": record.get("user_id"),
                    "status": record.get("status", "pending"),
                    "created_at": record.get("created_at", ""),
                    "updated_at": record.get("updated_at", ""),
                    "started_at": record.get("started_at"),
                    "finished_at": record.get("finished_at"),
                    "model_name": record.get("model_name"),
                    "error": record.get("error"),
                    "total_tokens": record.get("total_tokens"),
                    "metadata": _json_dumps(record.get("metadata", {})),
                    "report_path": report_path,
                },
            )

    # ---- 查询 ----

    def list_by_thread(self, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, thread_id, user_id, status, created_at, started_at,
                       finished_at, model_name, error, total_tokens, report_path
                FROM runs WHERE thread_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (thread_id, limit),
            ).fetchall()
        return [_row(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT run_id, thread_id, user_id, status, created_at, started_at,
                       finished_at, model_name, error, total_tokens, report_path
                FROM runs WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
        return _row(row) if row is not None else None


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _row(row) -> dict[str, Any]:
    return {
        "run_id": row[0],
        "thread_id": row[1],
        "user_id": row[2],
        "status": row[3],
        "created_at": row[4],
        "started_at": row[5],
        "finished_at": row[6],
        "model_name": row[7],
        "error": row[8],
        "total_tokens": row[9],
        "report_path": row[10],
    }
