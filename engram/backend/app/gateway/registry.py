"""会话注册表 — 每会话独立 thread，替换"每进程固定一个 thread"。

会话 = 网关层的对话入口：一个 session_id 对应一个独立 thread_id。
thread_id 是 agent 侧一切按会话隔离状态（LangGraph checkpointer /
记忆 recall/update）的作用域键，由本注册表分配、后续 chat/research
端点透传给 AppRuntime.run_question(thread_id=...)。

仅内存实现（issue 03 范围）；持久化随 PG checkpointer issue 演进。
thread_dir / thread_journal 的磁盘创建推迟到会话首次真正跑 run
（issue 04），创建会话保持纯内存快速路径。
"""

from __future__ import annotations

import threading
import uuid

from engram.backend.app.bootstrap import _make_thread_id


class SessionRecord:
    """注册表条目。字段同 SessionResponse，简单 dataclass 即可（schema 层做序列化）。"""

    __slots__ = ("session_id", "thread_id", "user_id", "created_at", "status", "metadata")

    def __init__(self, session_id: str, thread_id: str, user_id: str, created_at: str,
                 metadata: dict) -> None:
        self.session_id = session_id
        self.thread_id = thread_id
        self.user_id = user_id
        self.created_at = created_at
        self.status = "active"
        self.metadata = dict(metadata)


class SessionRegistry:
    """线程安全的会话注册表。

    FastAPI 的同步端点跑在线程池里，create/list/delete 可能并发——
    一把 Lock 保护 dict 即可（CRUD 微秒级，无竞争热点）。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def create(self, user_id: str = "default-user",
               metadata: dict | None = None) -> SessionRecord:
        """新建会话：分配独立 thread_id（每会话隔离的作用域键）。"""
        record = SessionRecord(
            session_id=uuid.uuid4().hex,
            thread_id=_make_thread_id(),
            user_id=user_id,
            created_at=_utc_now_iso(),
            metadata=metadata or {},
        )
        with self._lock:
            self._sessions[record.session_id] = record
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list(self, user_id: str | None = None) -> list[SessionRecord]:
        """按创建序返回会话；user_id 给定时过滤（多用户隔离的最小形态）。"""
        with self._lock:
            records = list(self._sessions.values())
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        return records

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None


def _utc_now_iso() -> str:
    from engram.backend.agents.journal.events import utc_now_iso

    return utc_now_iso()
