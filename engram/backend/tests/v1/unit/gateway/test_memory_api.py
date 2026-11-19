"""记忆查询端点测试 — gateway-client-api / 记忆查询。

验证（spec 场景）：
- 搜索记忆：关键词 + 类型过滤，返回匹配记忆及热/冷层标记
- 记忆统计：hot / cold / forgotten / consolidation 数量
- 用户过滤：Alice 的记忆不出现在 Bob 的查询（跨用户隔离）
- 503：记忆未配置（memory_provider 缺席）
- 层过滤 / 遗忘过滤 / 强度过滤 / limit

用 fakeredis 热层 + fake 冷层组成真实 TieredMemoryStore（layer 语义真实）。
"""

from __future__ import annotations

from typing import Any

import fakeredis
from fastapi.testclient import TestClient

from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore
from engram.backend.agents.memory.adapters.tiered_store import TieredMemoryStore
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.app.gateway.main import create_app


class _FakeCold:
    """冷层 stub：固定列表（MemoryStore 协议子集）。"""

    def __init__(self, traces: list[MemoryTrace]) -> None:
        self._traces = {t.id: t for t in traces}

    def add(self, trace) -> None:
        self._traces[trace.id] = trace

    def get(self, trace_id: str):
        return self._traces.get(trace_id)

    def update(self, trace) -> None:
        self._traces[trace.id] = trace

    def remove(self, trace_id: str) -> None:
        self._traces.pop(trace_id, None)

    def list_all(self) -> list:
        return list(self._traces.values())


def _trace(trace_id: str, content: str, *, user_id: str | None = None,
           type_: MemoryType = MemoryType.EPISODIC,
           strength: float = 0.8, metadata: dict | None = None) -> MemoryTrace:
    md = dict(metadata or {})
    if user_id is not None:
        md["user_id"] = user_id
    return MemoryTrace(
        id=trace_id, content=content, type=type_, strength=strength,
        created_at=1_700_000_000.0, source="worker:t1", metadata=md,
    )


def _build_store():
    hot = RedisMemoryStore(fakeredis.FakeStrictRedis(decode_responses=True))
    cold = _FakeCold([])
    return TieredMemoryStore(hot, cold)


def _make_runtime(store):
    provider = SimpleProvider(store)

    class _Runtime:
        capability_registry = SimpleNamespace(memory_provider=provider)
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    return _Runtime()


class SimpleNamespace:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class SimpleProvider:
    def __init__(self, store, manager=None) -> None:
        self._store = store
        self._manager = manager

    def store(self):
        return self._store

    def manager(self):
        return self._manager


class _JournalingManager:
    """manager 桩：记录 _emit_journal 事件（memory.remove.* 留痕验证）。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def _emit_journal(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


def _client(runtime):
    app = create_app(runtime_factory=lambda: runtime)
    return TestClient(app), app


def test_search_memory_with_type_and_layers():
    store = _build_store()
    # alice 的两条：一条仅冷层，一条双写（热）
    store._cold.add(_trace("t-cold", "alice cold only memory", user_id="alice"))
    store.add(_trace("t-hot", "alice semantic memory", user_id="alice",
                     type_=MemoryType.SEMANTIC))
    store._cold.add(_trace("t-bob", "bob private memory", user_id="bob"))

    client, _ = _client(_make_runtime(store))
    with client as c:
        resp = c.get("/memory/traces", params={"user_id": "alice", "q": "memory"})
    body = resp.json()
    assert resp.status_code == 200
    ids = {m["id"] for m in body}
    assert "t-bob" not in ids  # 跨用户隔离
    assert {"t-cold", "t-hot"} <= ids
    by_id = {m["id"]: m for m in body}
    assert by_id["t-hot"]["layer"] == "hot"
    assert by_id["t-cold"]["layer"] == "cold"
    assert by_id["t-hot"]["type"] == "semantic"

    # 类型过滤
    with client as c:
        semantic = c.get("/memory/traces", params={
            "user_id": "alice", "type": "semantic",
        }).json()
    assert {m["id"] for m in semantic} == {"t-hot"}


def test_memory_stats_counts():
    store = _build_store()
    store._cold.add(_trace("s1", "hot one", user_id="alice"))  # 仅冷
    store.add(_trace("s2", "hot two", user_id="alice"))  # 双写 → hot
    store._cold.add(_trace("s3", "forgotten one", user_id="alice",
                           metadata={"forgotten": True}))
    store._cold.add(_trace("s4", "consolidated knowledge", user_id="alice",
                           metadata={"consolidated_from": ["s1", "s2"]}))

    client, _ = _client(_make_runtime(store))
    with client as c:
        stats = c.get("/memory/stats", params={"user_id": "alice"}).json()

    assert stats["total"] == 4
    assert stats["hot"] == 1  # s2 双写
    assert stats["cold"] == 3  # s1/s3/s4 仅冷
    assert stats["forgotten"] == 1
    assert stats["consolidation"] == 1


def test_strength_and_forgotten_filters():
    store = _build_store()
    store._cold.add(_trace("w1", "weak memory alpha", user_id="alice", strength=0.2))
    store._cold.add(_trace("w2", "strong memory beta", user_id="alice", strength=0.9))
    store._cold.add(_trace("w3", "gone memory gamma", user_id="alice",
                           strength=0.9, metadata={"forgotten": True}))

    client, _ = _client(_make_runtime(store))
    with client as c:
        strong = c.get("/memory/traces", params={"user_id": "alice", "min_strength": 0.5}).json()
        forgotten = c.get("/memory/traces", params={"user_id": "alice", "forgotten": True}).json()
        alive = c.get("/memory/traces", params={"user_id": "alice", "forgotten": False}).json()

    assert {m["id"] for m in strong} == {"w2", "w3"}
    assert {m["id"] for m in forgotten} == {"w3"}
    assert {m["id"] for m in alive} == {"w1", "w2"}
    assert forgotten[0]["forgotten"] is True


def test_layer_filter_and_limit():
    store = _build_store()
    for i in range(5):
        store._cold.add(_trace(f"l{i}", f"cold item {i}", user_id="alice"))
    store.add(_trace("lh", "hot item", user_id="alice"))

    client, _ = _client(_make_runtime(store))
    with client as c:
        hot_only = c.get("/memory/traces", params={"layer": "hot"}).json()
        limited = c.get("/memory/traces", params={"limit": 2}).json()

    assert {m["id"] for m in hot_only} == {"lh"}
    assert len(limited) == 2


def test_memory_not_configured_503():
    class _Runtime:
        capability_registry = SimpleNamespace(memory_provider=None)
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    client, _ = _client(_Runtime())
    with client as c:
        assert c.get("/memory/stats").status_code == 503
        assert c.get("/memory/traces").status_code == 503
        detail = c.get("/memory/stats").json()["detail"]
        assert "ENGRAM_MEMORY_USE" in detail


# ── DELETE /memory/traces（memory-management-ui 任务 2.1-2.4） ──

def test_delete_single_trace_and_404():
    store = _build_store()
    store.add(_trace("d1", "to be deleted", user_id="alice"))
    store._cold.add(_trace("d2", "stays", user_id="alice"))

    client, _ = _client(_make_runtime(store))
    with client as c:
        resp = c.delete("/memory/traces", params={"trace_id": "d1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["grain"] == "trace" and body["deleted"] == 1

    with client as c:
        remaining = c.get("/memory/traces", params={"user_id": "alice"}).json()
        stats = c.get("/memory/stats", params={"user_id": "alice"}).json()
        gone = c.delete("/memory/traces", params={"trace_id": "d1"})
    assert {m["id"] for m in remaining} == {"d2"}
    assert stats["total"] == 1
    # 不存在的 trace id → 404
    assert gone.status_code == 404


def test_delete_single_preview_no_side_effect():
    store = _build_store()
    store.add(_trace("p1", "preview me", user_id="alice"))

    client, _ = _client(_make_runtime(store))
    with client as c:
        preview = c.delete("/memory/traces",
                           params={"trace_id": "p1", "preview": "true"}).json()
        stats = c.get("/memory/stats", params={"user_id": "alice"}).json()
        deleted = c.delete("/memory/traces", params={"trace_id": "p1"})
    assert preview["count"] == 1 and preview["preview"] is True
    assert stats["total"] == 1  # 预览无副作用
    assert deleted.status_code == 200


def test_delete_partition_thread_granularity():
    store = _build_store()
    store.add(_trace("a1", "alice t1", user_id="alice", metadata={"thread_id": "t1"}))
    store.add(_trace("a2", "alice t2", user_id="alice", metadata={"thread_id": "t2"}))
    store.add(_trace("b1", "bob t1", user_id="bob", metadata={"thread_id": "t1"}))

    client, _ = _client(_make_runtime(store))
    with client as c:
        preview = c.delete("/memory/traces", params={
            "user_id": "alice", "thread_id": "t1", "preview": "true",
        }).json()
        stats_before = c.get("/memory/stats").json()
        resp = c.delete("/memory/traces",
                        params={"user_id": "alice", "thread_id": "t1"})
        stats_after = c.get("/memory/stats").json()

    assert preview["grain"] == "thread"
    assert preview["count"] == 1 and preview["trace_ids"] == ["a1"]
    assert resp.status_code == 200
    body = resp.json()
    # 预览数量 == 实际删除数量（任务 2.4）
    assert body["deleted"] == preview["count"] == 1
    assert stats_after["total"] == stats_before["total"] - 1
    with client as c:
        alive = {m["id"] for m in c.get("/memory/traces").json()}
    assert alive == {"a2", "b1"}  # 相邻 thread/user 完好


def test_delete_partition_user_granularity():
    store = _build_store()
    store.add(_trace("a1", "alice t1", user_id="alice", metadata={"thread_id": "t1"}))
    store.add(_trace("a2", "alice t2", user_id="alice", metadata={"thread_id": "t2"}))
    store.add(_trace("b1", "bob t1", user_id="bob", metadata={"thread_id": "t1"}))

    client, _ = _client(_make_runtime(store))
    with client as c:
        preview = c.delete("/memory/traces",
                           params={"user_id": "alice", "preview": "true"}).json()
        resp = c.delete("/memory/traces", params={"user_id": "alice"})
        alive = {m["id"] for m in c.get("/memory/traces").json()}

    assert preview["grain"] == "user" and preview["count"] == 2
    assert resp.json()["deleted"] == 2
    assert alive == {"b1"}


def test_delete_requires_granularity_and_rejects_mixed():
    store = _build_store()
    client, _ = _client(_make_runtime(store))
    with client as c:
        no_grain = c.delete("/memory/traces")
        mixed = c.delete("/memory/traces",
                         params={"trace_id": "x", "user_id": "alice"})
        thread_no_user = c.delete("/memory/traces", params={"thread_id": "t1"})
    assert no_grain.status_code == 400
    assert mixed.status_code == 400
    assert thread_no_user.status_code == 400


def test_delete_503_when_not_configured():
    class _Runtime:
        capability_registry = SimpleNamespace(memory_provider=None)
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    client, _ = _client(_Runtime())
    with client as c:
        assert c.delete("/memory/traces", params={"trace_id": "x"}).status_code == 503
        assert c.delete("/memory/traces", params={"user_id": "alice"}).status_code == 503


def test_delete_emits_journal_events_without_content():
    store = _build_store()
    store.add(_trace("j1", "secret content abc", user_id="alice",
                     metadata={"thread_id": "t1"}))
    store.add(_trace("j2", "another secret def", user_id="alice",
                     metadata={"thread_id": "t1"}))
    manager = _JournalingManager()
    provider = SimpleProvider(store, manager=manager)

    class _Runtime:
        capability_registry = SimpleNamespace(memory_provider=provider)
        run_manager = SimpleNamespace()
        researcher_model_name = "fake"

    runtime = _Runtime()

    client, _ = _client(runtime)
    with client as c:
        c.delete("/memory/traces", params={"trace_id": "j1"})
        c.delete("/memory/traces",
                 params={"user_id": "alice", "thread_id": "t1"})

    events = dict(manager.events)
    assert "memory.remove.trace" in events
    assert "memory.remove.partition" in events
    part_event = events["memory.remove.partition"]
    assert part_event["grain"] == "thread" and part_event["user_id"] == "alice"
    assert part_event["thread_id"] == "t1" and part_event["deleted"] == 1
    # journal 不含记忆正文
    for _evt, payload in manager.events:
        assert "secret content" not in str(payload)
