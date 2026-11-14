"""冷热分层 store 测试 — TieredMemoryStore 组合语义 + 冷层兜底一致性。

- 组合逻辑：内存 fake（协议桩）做热/冷双层，无外部依赖
- 冷层 PG：ENGRAM_TEST_PG_DSN 配置时 live 真跑（docker postgres）
- 迁移：MarkdownFileStore 存量 → 冷层导入（live）
- 演示语义：flush 热层后召回不缺（冷层兜底 + 回填）——live 全链路
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from engram.backend.agents.memory.adapters.tiered_store import TieredMemoryStore
from engram.backend.agents.memory.exceptions import MemoryNotFoundError
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.agents.memory.types import MemoryFilter

TEST_PG_DSN = os.environ.get("ENGRAM_TEST_PG_DSN", "").strip()

needs_pg = pytest.mark.skipif(
    not TEST_PG_DSN, reason="ENGRAM_TEST_PG_DSN not set; live Postgres required"
)


def _trace(content: str = "mem", **kw) -> MemoryTrace:
    defaults = dict(
        id=uuid.uuid4().hex,
        content=content,
        type=MemoryType.EPISODIC,
        created_at=time.time(),
        strength=0.7,
        source="worker:thread-x:1",
    )
    defaults.update(kw)
    return MemoryTrace(**defaults)


class _FakeStore:
    """协议桩：dict 内存实现（add 冲突 / update 缺失语义与真 store 一致）。"""

    def __init__(self) -> None:
        self.traces: dict = {}

    def add(self, trace) -> None:
        if trace.id in self.traces:
            from engram.backend.agents.memory.exceptions import MemoryConflictError

            raise MemoryConflictError(
                "trace already exists: " + trace.id, old_id=trace.id, new_id=trace.id)
        self.traces[trace.id] = trace

    def get(self, trace_id):
        return self.traces.get(trace_id)

    def update(self, trace) -> None:
        if trace.id not in self.traces:
            raise MemoryNotFoundError(trace.id)
        self.traces[trace.id] = trace

    def batch_update(self, traces):
        for t in traces:
            self.update(t)

    def remove(self, trace_id) -> None:
        self.traces.pop(trace_id, None)

    def list_by_type(self, type):
        return [t for t in self.traces.values() if t.type == type]

    def list_by_filter(self, flt):
        return [t for t in self.traces.values()]

    def list_all(self):
        return list(self.traces.values())


# ── 组合逻辑（无外部依赖） ───────────────────────────────────

def test_dual_write_sediments_cold_first() -> None:
    """add 双写：冷层（沉淀 truth）+ 热层都拿到。"""
    hot, cold = _FakeStore(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    t = _trace("dual")
    tiered.add(t)
    assert cold.get(t.id) is not None
    assert hot.get(t.id) is not None


def test_hot_miss_falls_to_cold_and_backfills() -> None:
    """热 miss → 冷查 → 回填热层（trace 重新变热）。"""
    hot, cold = _FakeStore(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    t = _trace("fallback")
    tiered.add(t)
    hot.remove(t.id)  # 模拟 TTL 过期/FLUSHDB
    assert hot.get(t.id) is None  # 热层已无
    got = tiered.get(t.id)  # 冷层兜底
    assert got is not None and got.content == "fallback"
    assert hot.get(t.id) is not None  # 回填后热层又有


def test_flush_hot_recall_still_complete() -> None:
    """冷热一致性核心：清空热层后 list_all 召回不缺（冷层兜底）。"""
    hot, cold = _FakeStore(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    ids = []
    for i in range(5):
        t = _trace("memory-%d" % i)
        tiered.add(t)
        ids.append(t.id)
    hot.traces.clear()  # FLUSHDB
    assert len(tiered.list_all()) == 5  # 冷层全量兜底
    for tid in ids:
        assert tiered.get(tid) is not None


def test_hot_version_wins_in_listing() -> None:
    """list_all 合并：热层版本（更新）优先于冷层旧版本。"""
    hot, cold = _FakeStore(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    t = _trace("v1")
    tiered.add(t)
    strengthened = t.with_strength(0.95, time.time())
    tiered.update(strengthened)  # 双写更新
    # 模拟热层丢/冷层旧：手撸冷层旧版本
    cold.traces[t.id] = t
    listed = {x.id: x for x in tiered.list_all()}
    assert listed[t.id].strength == 0.95  # 热层（新）胜出
    assert len(listed) == 1  # 不重复


def test_hot_failure_falls_through_to_cold() -> None:
    """review fix regression: hot tier raising must not mask the cold fallback."""
    class _ExplodingHot(_FakeStore):
        def get(self, trace_id):
            raise ConnectionError("redis down")

        def list_all(self):
            raise ConnectionError("redis down")

        def add(self, trace):
            raise ConnectionError("redis down")

    hot, cold = _ExplodingHot(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    t = _trace("durable")
    cold.add(t)
    # get: hot explodes -> cold fallback still succeeds (backfill swallowed)
    got = tiered.get(t.id)
    assert got is not None and got.content == "durable"
    # list_all: hot explodes -> cold full listing still returns
    assert len(tiered.list_all()) == 1

def test_tiered_shutdown_delegates_to_tiers() -> None:
    """review fix regression: shutdown delegates to both tiers (no resource leak)."""
    closed = []

    class _ClosingStore(_FakeStore):
        def close(self):
            closed.append("close")

    class _ShuttingStore(_FakeStore):
        def shutdown(self):
            closed.append("shutdown")

    tiered = TieredMemoryStore(_ClosingStore(), _ShuttingStore())
    tiered.shutdown()
    assert sorted(closed) == ["close", "shutdown"]


def test_remove_dual_delete() -> None:
    hot, cold = _FakeStore(), _FakeStore()
    tiered = TieredMemoryStore(hot, cold)
    t = _trace("gone")
    tiered.add(t)
    tiered.remove(t.id)
    assert tiered.get(t.id) is None
    assert hot.get(t.id) is None and cold.get(t.id) is None


# ── live（docker PG + fakeredis 全链路） ──────────────────────

@needs_pg
def test_live_pg_cold_tier_roundtrip() -> None:
    """真 PG 冷层：协议 CRUD roundtrip + 幂等迁移跳过。"""
    import fakeredis

    from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore

    cold = PostgresMemoryStore(TEST_PG_DSN)
    try:
        t = _trace("cold-roundtrip")
        cold.add(t)
        got = cold.get(t.id)
        assert got is not None and got.content == "cold-roundtrip"
        # list_by_filter metadata
        flt = MemoryFilter(min_strength=0.0)
        assert any(x.id == t.id for x in cold.list_by_filter(flt))
        cold.remove(t.id)
        assert cold.get(t.id) is None
        # remove 幂等
        cold.remove(t.id)
    finally:
        cold.close()


@needs_pg
def test_live_flush_hot_recall_from_cold() -> None:
    """演示主轴：fakeredis 热 + 真 PG 冷，FLUSHDB 后召回不缺且回填。"""
    import fakeredis
    import redis

    from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore
    from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore

    hot = RedisMemoryStore(fakeredis.FakeStrictRedis(), ttl_seconds=30)
    cold = PostgresMemoryStore(TEST_PG_DSN)
    tiered = TieredMemoryStore(hot, cold)
    try:
        for i in range(3):
            tiered.add(_trace("flush-demo-%d" % i))
        hot._client.flushdb()  # 热层全清
        # 冷层兜底：召回不缺
        got = tiered.list_all()
        contents = sorted(t.content for t in got)
        assert contents == ["flush-demo-0", "flush-demo-1", "flush-demo-2"]
        # get 触发回填（热层重新变热）
        one = got[0]
        assert tiered.get(one.id) is not None
        assert hot.get(one.id) is not None
    finally:
        for t in list(tiered.list_all()):
            tiered.remove(t.id)  # 清理演示数据
        cold.close()


@needs_pg
def test_live_markdown_migration() -> None:
    """traces.md 存量迁移：MarkdownFileStore 写入 → migrate → 冷层全量 + 幂等跳过。"""
    from pathlib import Path

    from engram.backend.agents.memory.adapters.migration import migrate_markdown_to_pg
    from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore
    from engram.backend.agents.memory.strategies.default.store import MarkdownFileStore

    root = Path(".engram") / ("migration-test-" + uuid.uuid4().hex[:6])
    md = MarkdownFileStore(str(root))
    t1 = _trace("legacy-1", id=uuid.uuid4().hex)
    t2 = _trace("legacy-2", id=uuid.uuid4().hex)
    md.add(t1)
    md.add(t2)

    cold = PostgresMemoryStore(TEST_PG_DSN)
    try:
        migrated, skipped = migrate_markdown_to_pg(str(root), TEST_PG_DSN)
        assert (migrated, skipped) == (2, 0)
        assert cold.get(t1.id).content == "legacy-1"
        # 重跑幂等：已存在跳过
        migrated2, skipped2 = migrate_markdown_to_pg(str(root), TEST_PG_DSN)
        assert (migrated2, skipped2) == (0, 2)
    finally:
        cold.remove(t1.id)
        cold.remove(t2.id)
        cold.close()
        import shutil

        shutil.rmtree(root, ignore_errors=True)
