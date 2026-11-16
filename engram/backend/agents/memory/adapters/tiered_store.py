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

        hot 命中即 hot（读回填后冷层也有副本，但热层在场即视为热）。
        """
        try:
            if self._hot.get(trace_id) is not None:
                return "hot"
        except Exception:
            pass
        if self._cold.get(trace_id) is not None:
            return "cold"
        return None

    def iter_views(self) -> list[tuple[MemoryTrace, str | None]]:
        """(trace, layer) 全量视图——list_all 的层标注版（Memory Explorer 用）。"""
        return [
            (trace, self.layer_of(trace.id))
            for trace in self.list_all()
        ]

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
