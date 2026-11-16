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
    def __init__(self, store) -> None:
        self._store = store

    def store(self):
        return self._store


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
