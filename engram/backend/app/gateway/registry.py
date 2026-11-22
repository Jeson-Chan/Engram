"""会话注册表 — 每会话独立 thread，替换"每进程固定一个 thread"。

会话 = 网关层的对话入口：一个 session_id 对应一个独立 thread_id。
thread_id 是 agent 侧一切按会话隔离状态（LangGraph checkpointer /
记忆 recall/update）的作用域键，由本注册表分配、后续 chat/research
端点透传给 AppRuntime.run_question(thread_id=...)。

仅内存实现（issue 03 范围）；持久化随 PG checkpointer issue 演进。
→ E2E 缺陷 F 修复：可选注入 SessionStore（默认 SQLite .engram/gateway.db，
见 session_store.py）；store=None 保持纯内存（测试/旧行为）。
thread_dir / thread_journal 的磁盘创建推迟到会话首次真正跑 run
（issue 04），创建会话保持纯内存快速路径。
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

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

    store（E2E 缺陷 F）：可选持久后端（SqliteSessionStore 等）——
    create/delete 落盘，构造时回灌；store=None 保持纯内存（旧行为）。
    """

    def __init__(self, store: Any = None) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()
        self._store = store
        if store is not None:
            for record in store.load_all():
                self._sessions[record.session_id] = record

    def create(self, user_id: str = "default-user",
               metadata: dict | None = None) -> SessionRecord:
        """新建会话：分配独立 thread_id（每会话隔离的作用域键）。

        review medium：先落盘再进内存——save() 失败（SQLite 锁/盘满）时
        端点 500 且内存不残留幽灵会话（否则重启后凭空消失）。
        """
        record = SessionRecord(
            session_id=uuid.uuid4().hex,
            thread_id=_make_thread_id(),
            user_id=user_id,
            created_at=_utc_now_iso(),
            metadata=metadata or {},
        )
        if self._store is not None:
            self._store.save(record)  # 落盘失败上抛（端点 500，不静默）
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

    def rename(self, session_id: str, title: str) -> "SessionRecord | None":
        """重命名：更新 metadata.title（整记录覆盖写——save upsert 语义）。

        返回更新后的记录；未知 id 返 None（端点 404）。空 title 由调用方
        （端点层）拒绝——registry 只管持久化。
        与 delete 同模式：store 先写（失败上抛，内存不改 → 端点 500 状态一致）。
        """
        with self._lock:
            record = self._sessions.get(session_id)
        if record is None:
            return None
        metadata = dict(record.metadata)
        metadata["title"] = title
        # SessionRecord 构造签名不含 status（固定 "active"）——直接复用字段
        updated = SessionRecord(
            session_id=record.session_id,
            thread_id=record.thread_id,
            user_id=record.user_id,
            created_at=record.created_at,
            metadata=metadata,
        )
        updated.status = record.status
        if self._store is not None:
            self._store.update(updated)  # 失败上抛：内存未改，状态一致
        with self._lock:
            self._sessions[session_id] = updated
        return updated

    def delete(self, session_id: str) -> bool:
        """删除会话。store 先删（失败上抛，内存条目保留 → 端点 500 而不是
        假 204，重启后数据也一致——review medium 的对称修复）。"""
        with self._lock:
            existed = self._sessions.get(session_id) is not None
        if not existed:
            return False
        if self._store is not None:
            self._store.delete(session_id)  # 失败上抛：内存未删，状态一致
        with self._lock:
            self._sessions.pop(session_id, None)
        return True


def _utc_now_iso() -> str:
    from engram.backend.agents.journal.events import utc_now_iso

    return utc_now_iso()
