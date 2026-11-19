"""TieredMemoryStore - hot(Redis TTL) + cold(Postgres sediment) composite (issue 07).

Two-tier memory read path:
- add/update/batch_update: dual write, COLD FIRST (sediment is the
  durability guarantee), then hot (TTL keeps it only while warm)
- get: hot hit returns immediately (low latency); miss falls to cold,
  and a cold hit back-fills the hot tier (the trace goes warm again)
- remove: dual delete
- listing (list_all / list_by_type / list_by_filter): cold is the full
  truth, hot versions win on id collisions (they are strictly newer or
  at least as fresh - hot is a write-through cache)
- read-refresh TTL of the hot tier is preserved via its own get()
"""

from __future__ import annotations

import logging

from engram.backend.agents.memory.exceptions import MemoryNotFoundError
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.agents.memory.types import MemoryFilter

logger = logging.getLogger(__name__)


class TieredMemoryStore:
    """Hot + cold composite implementing the MemoryStore Protocol."""

    def __init__(self, hot, cold) -> None:
        """hot: RedisMemoryStore-like with TTL; cold: PostgresMemoryStore-like."""
        self._hot = hot
        self._cold = cold

    @property
    def hot(self):
        return self._hot

    @property
    def cold(self):
        return self._cold

    def shutdown(self) -> None:
        """Delegate closes to both tiers (DefaultMemoryProvider.shutdown
        duck-types via hasattr, so the PG pool / redis client actually close)."""
        for store in (self._hot, self._cold):
            closer = getattr(store, "shutdown", None) or getattr(store, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass

    # ---- protocol methods ----

    def add(self, trace: MemoryTrace) -> None:
        self._cold.add(trace)       # sediment first (durability)
        try:
            self._hot.add(trace)    # warm copy; id may exist after eviction+backfill
        except Exception:
            # backfilled trace still warm -> hot conflict is fine, cold is truth
            self._hot.update(trace)

    def get(self, trace_id: str) -> MemoryTrace | None:
        # hot tier is best-effort: a Redis failure must fall through to
        # cold (the durable truth) instead of masking it
        try:
            trace = self._hot.get(trace_id)
        except Exception:
            trace = None
        if trace is not None:
            return trace            # hot hit (TTL refreshed by hot.get)
        trace = self._cold.get(trace_id)
        if trace is not None:
            # cold hit -> back-fill the hot tier (best-effort; cold is truth)
            try:
                self._hot.add(trace)
            except Exception:
                try:
                    self._hot.update(trace)
                except Exception:
                    pass
        return trace

    def update(self, trace: MemoryTrace) -> None:
        self._cold.update(trace)
        try:
            self._hot.update(trace)
        except MemoryNotFoundError:
            # not warm right now -> put it back (dual-write semantics)
            self._hot.add(trace)

    def batch_update(self, traces: list[MemoryTrace]) -> None:
        self._cold.batch_update(traces)
        for trace in traces:
            try:
                self._hot.update(trace)
            except MemoryNotFoundError:
                self._hot.add(trace)

    def remove(self, trace_id: str) -> None:
        self._cold.remove(trace_id)
        self._hot.remove(trace_id)  # idempotent per protocol

    def remove_partition(
        self, user_id: str, thread_id: str | None = None
    ) -> list[str]:
        """按分区批量删除：cold（真源）先删，hot 尽力而为。

        容错方向与 list_all 一致：hot 失败不阻断（冷层为真源，剩余热键
        随 TTL 消亡或 get 回源 miss）。cold 无分区原语时降级为
        list_partition（同一谓词）+ 逐条 remove。返回 cold 实际删除的
        id 列表。
        """
        removed: list[str] = []
        remover = getattr(self._cold, "remove_partition", None)
        if callable(remover):
            removed = list(remover(user_id, thread_id))
        else:
            for tid in self.list_partition(user_id, thread_id):
                self._cold.remove(tid)
                removed.append(tid)
        try:
            hot_remover = getattr(self._hot, "remove_partition", None)
            if callable(hot_remover):
                hot_remover(user_id, thread_id)
        except Exception:
            logger.warning(
                "hot tier partition removal failed (user=%s thread=%s);"
                " cold is truth", user_id, thread_id, exc_info=True,
            )
        return removed

    def list_partition(
        self, user_id: str, thread_id: str | None = None
    ) -> list[str]:
        """分区定位（预览）：cold 为全量真源，定位只看 cold。"""
        lister = getattr(self._cold, "list_partition", None)
        if callable(lister):
            return list(lister(user_id, thread_id))
        # cold 无分区原语时按分区谓词过滤（与各 store _partition_of 同语义）
        out: list[str] = []
        for trace in self._cold.list_all():
            metadata = getattr(trace, "metadata", None) or {}
            t_user = str(metadata.get("user_id", "default-user"))
            t_thread = metadata.get("thread_id")
            if not t_thread:
                source = trace.source or ""
                t_thread = (
                    source.split(":")[1]
                    if source.startswith("worker:") else "default"
                )
            if t_user != user_id:
                continue
            if thread_id is not None and str(t_thread) != thread_id:
                continue
            out.append(trace.id)
        return out

    def list_by_type(self, type: MemoryType) -> list[MemoryTrace]:
        return [t for t in self.list_all() if t.type == type]

    def list_by_filter(self, filter: MemoryFilter) -> list[MemoryTrace]:
        return [
            t for t in self.list_all()
            if self._match(t, filter)
        ]

    def list_all(self) -> list[MemoryTrace]:
        """Cold is the full truth; hot versions win on id collision (newer).
        Hot tier is best-effort (failure -> cold only)."""
        merged: dict[str, MemoryTrace] = {}
        for trace in self._cold.list_all():
            merged[trace.id] = trace
        try:
            for trace in self._hot.list_all():
                merged[trace.id] = trace
        except Exception:
            pass  # hot unavailable: cold is the truth, list still complete
        return list(merged.values())

    # ---- 只读层视图（gateway-client-api / 记忆查询，design.md 决策 6） ----

    def layer_of(self, trace_id: str) -> str | None:
        """trace 当前所在层："hot" / "cold" / None（不存在）。

        review medium：存在探测走无副作用路径——RedisMemoryStore.contains
        （get() 命中会刷新 TTL：浏览/统计不该给热层续命，破坏热→冷冷却；
        miss 还会触发 _lazy_forget 写操作）。热层无 contains 能力时回退 get。
        """
        hot_contains = getattr(self._hot, "contains", None)
        try:
            if callable(hot_contains):
                if hot_contains(trace_id):
                    return "hot"
            elif self._hot.get(trace_id) is not None:
                return "hot"
        except Exception:
            pass
        if self._cold.get(trace_id) is not None:
            return "cold"
        return None

    def iter_views(self) -> list[tuple[MemoryTrace, str | None]]:
        """(trace, layer) 全量视图——list_all 的层标注版（Memory Explorer 用）。

        review performance：热层 id 集一次取出再标注（每条 layer_of 都是
        两次远程 GET；list_all 已拉过全部热 trace——直接建 set）。
        """
        hot_ids: set[str] | None = None
        try:
            hot_contains = getattr(self._hot, "contains", None)
            if callable(hot_contains):
                hot_ids = {
                    trace.id for trace in self._hot.list_all()
                }
        except Exception:
            hot_ids = None
        out: list[tuple[MemoryTrace, str | None]] = []
        for trace in self.list_all():
            if hot_ids is not None and trace.id in hot_ids:
                out.append((trace, "hot"))
            else:
                out.append((trace, self.layer_of(trace.id)))
        return out

    # ---- internals ----

    @staticmethod
    def _match(trace: MemoryTrace, filter: MemoryFilter) -> bool:
        import time as _t

        if filter.type_filter is not None and trace.type != filter.type_filter:
            return False
        if trace.strength < filter.min_strength:
            return False
        if filter.max_age_hours is not None:
            if (_t.time() - trace.created_at) / 3600.0 > filter.max_age_hours:
                return False
        for key, value in (filter.metadata_filter or {}).items():
            if trace.metadata.get(key) != value:
                return False
        return True
