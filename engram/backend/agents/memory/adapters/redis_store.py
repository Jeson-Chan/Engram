"""RedisMemoryStore - L3 hot-tier memory on Redis (adapters, swappable backend).

Replaces MarkdownFileStore's global single-file layout (issue 06):
- Keys partitioned per user/thread: engram:mem:{user}:{thread}:{trace_id}
  (partition from trace.metadata["user_id"]; thread from source
  "worker:{thread}" prefix or metadata["thread_id"], default "default")
- Per-trace TTL: keys land with TTL - hot memory evicts over time, expired
  keys disappear (redis-cli TTL shows the countdown). Read hits refresh
  TTL: frequently retrieved memories stay hot, untouched ones cool off
- Global id index: engram:mem:idx hash (trace_id -> partition) so
  get/update/remove locate the partition from the bare id; partition id
  sets engram:mem:ids:{user}:{thread} (isolated partition listing)

Protocol semantics identical to MarkdownFileStore: add conflict raises
MemoryConflictError, update-missing raises MemoryNotFoundError, remove is
idempotent. Expired traces count as absent; index leftovers lazily cleaned.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from engram.backend.agents.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from engram.backend.agents.memory.schema import (
    Association,
    MemoryTrace,
    MemoryType,
    OperationLog,
)
from engram.backend.agents.memory.types import MemoryFilter

logger = logging.getLogger(__name__)


def _text(value) -> str:
    """redis 返回值容错解码（decode_responses=False 时 hget/hkeys/smembers 返 bytes）。"""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value

_KEY_PREFIX = "engram:mem"
_IDX_KEY = "engram:mem:idx"                  # hash: trace_id -> "{user}:{thread}"
_IDS_KEY = "engram:mem:ids:{user}:{thread}"  # set: trace ids inside partition


class _Partition:
    """Partition view - isolated listing of one user/thread hot memory."""

    def __init__(self, store, user_id: str, thread_id: str) -> None:
        self._store = store
        self._user_id = user_id
        self._thread_id = thread_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def thread_id(self) -> str:
        return self._thread_id

    def list(self) -> list:
        """Alive memories within this partition (expired keys lazily pruned)."""
        return self._store._list_partition(self._user_id, self._thread_id)

    def ids(self) -> list:
        return self._store._partition_ids(self._user_id, self._thread_id)


class RedisMemoryStore:
    """Redis hot-tier memory (MemoryStore Protocol).

    Constructor takes a connected sync redis client (production:
    redis.Redis.from_url; tests: fakeredis.FakeStrictRedis). ttl_seconds
    defaults from env ENGRAM_MEMORY_TTL_SECONDS (second-granularity for
    tests/demo), else forget.ttl_hours * 3600.
    """

    def __init__(self, client: Any, ttl_seconds: int | None = None) -> None:
        import os

        self._client = client
        if ttl_seconds is None:
            env = os.environ.get("ENGRAM_MEMORY_TTL_SECONDS", "").strip()
            if env:
                ttl_seconds = int(env)
        self._ttl = ttl_seconds  # None = no eviction (permanent hot tier)

    def _set(self, key: str, payload: str) -> None:
        if self._ttl:
            self._client.set(key, payload, ex=self._ttl)
        else:
            self._client.set(key, payload)

    # ---- protocol methods ----

    def add(self, trace: MemoryTrace) -> None:
        user_id, thread_id = self._partition_of(trace)
        key = self._key(user_id, thread_id, trace.id)
        if self._client.exists(key):
            raise MemoryConflictError(
                "trace already exists: " + trace.id,
                old_id=trace.id, new_id=trace.id,
            )
        self._set(key, _dump(trace))
        self._client.hset(_IDX_KEY, trace.id, user_id + ":" + thread_id)
        self._client.sadd(_IDS_KEY.format(user=user_id, thread=thread_id), trace.id)

    def get(self, trace_id: str):
        key = self._key_of(trace_id)
        raw = self._client.get(key)
        if raw is None:
            self._lazy_forget(trace_id)
            return None
        # hot semantics: read hit refreshes TTL (retrieved memories stay hot)
        if self._ttl:
            self._client.expire(key, self._ttl)
        return _load(raw)

    def contains(self, trace_id: str) -> bool:
        """无副作用存在检查（review medium）：不刷新 TTL、不触发 _lazy_forget——
        层视图/统计/列表用的只读语义（get() 会续命热层，浏览 Memory Explorer
        反而把所有热记忆永久保温，破坏热→冷冷却）。"""
        return bool(self._client.exists(self._key_of(trace_id)))

    def update(self, trace: MemoryTrace) -> None:
        key = self._key_of(trace.id)
        if self._client.get(key) is None:
            raise MemoryNotFoundError(trace.id)
        self._set(key, _dump(trace))

    def batch_update(self, traces: list) -> None:
        for trace in traces:  # no transaction (2A: per-op, eventual consistency)
            self.update(trace)

    def remove(self, trace_id: str) -> None:
        self._client.delete(self._key_of(trace_id))
        partition = self._client.hget(_IDX_KEY, trace_id)
        if partition:
            user_id, thread_id = _text(partition).split(":", 1)
            self._client.srem(_IDS_KEY.format(user=user_id, thread=thread_id), trace_id)
        self._client.hdel(_IDX_KEY, trace_id)

    def remove_partition(
        self, user_id: str, thread_id: str | None = None
    ) -> list:
        """按分区批量删除（design.md 决策 2）：pipeline 一次往返。

        定位：扫 idx hash 找该 user（或 user+thread）的全部分区键——
        trace key 删除也走 idx（_key_of），所以先取 key 再 hdel。
        幂等：不存在的分区/键静默。返回删除的 trace_id 列表。
        """
        targets: set = set()
        partitions: set = set()
        for raw_id, raw_partition in self._client.hgetall(_IDX_KEY).items():
            trace_id = _text(raw_id)
            p_user, p_thread = _text(raw_partition).split(":", 1)
            if p_user != user_id:
                continue
            if thread_id is not None and p_thread != thread_id:
                continue
            targets.add(trace_id)
            partitions.add((p_user, p_thread))
        if not targets:
            return []
        pipe = self._client.pipeline()
        for trace_id in targets:
            pipe.delete(self._key_of(trace_id))
            pipe.hdel(_IDX_KEY, trace_id)
        for p_user, p_thread in partitions:
            pipe.delete(_IDS_KEY.format(user=p_user, thread=p_thread))
        pipe.execute()
        logger.info("removed %d traces from partition user=%s thread=%s",
                    len(targets), user_id, thread_id)
        return sorted(targets)

    def list_by_type(self, type: MemoryType) -> list:
        return [t for t in self.list_all() if t.type == type]

    def list_by_filter(self, filter: MemoryFilter) -> list:
        now = time.time()
        out = []
        for trace in self.list_all():
            if filter.type_filter is not None and trace.type != filter.type_filter:
                continue
            if trace.strength < filter.min_strength:
                continue
            if filter.max_age_hours is not None:
                age_hours = (now - trace.created_at) / 3600.0
                if age_hours > filter.max_age_hours:
                    continue
            if filter.metadata_filter:
                if any(trace.metadata.get(k) != v for k, v in filter.metadata_filter.items()):
                    continue
            out.append(trace)
        return out

    def list_all(self) -> list:
        """All alive memories via the global id index (expired lazily pruned)."""
        out = []
        for trace_id in map(_text, self._client.hkeys(_IDX_KEY)):
            raw = self._client.get(self._key_of(trace_id))
            if raw is None:
                self._lazy_forget(trace_id)
                continue
            out.append(_load(raw))
        return out

    # ---- partition view (isolated listing / demo) ----

    def partition(self, user_id: str, thread_id: str) -> _Partition:
        return _Partition(self, user_id, thread_id)

    # ---- internals ----

    def _partition_of(self, trace: MemoryTrace) -> tuple:
        # user sentinel 统一 "default-user"（网关/registry 默认用户——review
        # medium：与检索/查询侧的 sentinel 保持一致，否则跨层判断不一致）
        user_id = str(trace.metadata.get("user_id", "default-user"))
        thread_id = trace.metadata.get("thread_id")
        if not thread_id:
            source = trace.source or ""
            if source.startswith("worker:"):
                thread_id = source.split(":")[1]
            else:
                thread_id = "default"
        return user_id, str(thread_id)

    def _key(self, user_id: str, thread_id: str, trace_id: str) -> str:
        return _KEY_PREFIX + ":" + user_id + ":" + thread_id + ":" + trace_id

    def _key_of(self, trace_id: str) -> str:
        partition = self._client.hget(_IDX_KEY, trace_id)
        if partition is None:
            return self._key("default", "default", trace_id)
        user_id, thread_id = _text(partition).split(":", 1)
        return self._key(user_id, thread_id, trace_id)

    def _lazy_forget(self, trace_id: str) -> None:
        """Clean index leftovers after a key expired (idempotent)."""
        partition = self._client.hget(_IDX_KEY, trace_id)
        if partition:
            user_id, thread_id = _text(partition).split(":", 1)
            self._client.srem(_IDS_KEY.format(user=user_id, thread=thread_id), trace_id)
        self._client.hdel(_IDX_KEY, trace_id)

    def _partition_ids(self, user_id: str, thread_id: str) -> list:
        return [str(i) for i in map(_text, self._client.smembers(
            _IDS_KEY.format(user=user_id, thread=thread_id)))]

    def _list_partition(self, user_id: str, thread_id: str) -> list:
        out = []
        for trace_id in self._partition_ids(user_id, thread_id):
            raw = self._client.get(self._key(user_id, thread_id, trace_id))
            if raw is None:
                self._client.srem(_IDS_KEY.format(user=user_id, thread=thread_id), trace_id)
                continue
            out.append(_load(raw))
        return out


# ---- serialization (frozen dataclass <-> JSON) ----

def _dump(trace: MemoryTrace) -> str:
    """MemoryTrace -> JSON string (tuples land as lists, restored on load)."""
    return json.dumps(_trace_to_dict(trace), ensure_ascii=False)


def _trace_to_dict(trace: MemoryTrace) -> dict:
    return {
        "id": trace.id,
        "content": trace.content,
        "type": trace.type.value if isinstance(trace.type, MemoryType) else str(trace.type),
        "strength": trace.strength,
        "base_strength": trace.base_strength,
        "decay_rate": trace.decay_rate,
        "access_count": trace.access_count,
        "last_accessed": trace.last_accessed,
        "importance": trace.importance,
        "associations": [
            {"target_id": a.target_id, "strength": a.strength, "type": a.type}
            for a in trace.associations
        ],
        "embedding": list(trace.embedding) if trace.embedding is not None else None,
        "source": trace.source,
        "created_at": trace.created_at,
        "metadata": dict(trace.metadata),
        "operation_log": [
            {"timestamp": o.timestamp, "operation": o.operation,
             "actor": o.actor, "diff": o.diff}
            for o in trace.operation_log
        ],
    }


def _load(raw) -> MemoryTrace:
    """JSON -> MemoryTrace (bytes decoded; dict passed through - psycopg
    JSONB columns auto-deserialize, sharing this loader with the cold tier)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return MemoryTrace(
        id=data["id"],
        content=data["content"],
        type=MemoryType(data["type"]),
        strength=data.get("strength", 0.0),
        base_strength=data.get("base_strength", 0.7),
        decay_rate=data.get("decay_rate", 0.1),
        access_count=data.get("access_count", 0),
        last_accessed=data.get("last_accessed", 0.0),
        importance=data.get("importance", 0.5),
        associations=tuple(Association(**a) for a in data.get("associations", [])),
        embedding=tuple(data["embedding"]) if data.get("embedding") is not None else None,
        source=data.get("source"),
        created_at=data.get("created_at", 0.0),
        metadata=dict(data.get("metadata", {})),
        operation_log=tuple(
            OperationLog(
                timestamp=o["timestamp"], operation=o["operation"],
                actor=o.get("actor"), diff=o.get("diff"),
            )
            for o in data.get("operation_log", [])
        ),
    )
