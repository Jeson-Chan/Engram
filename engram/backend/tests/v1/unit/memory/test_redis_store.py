"""RedisMemoryStore 测试 — 分区隔离 + TTL 语义 + 协议行为。

fakeredis（无网络依赖，TTL 真实生效：到期键消失）；
live 行为测试（ENGRAM_TEST_REDIS_DSN 配置时跑，CI/本地 docker redis 真跑）。
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from engram.backend.agents.memory.adapters.redis_store import (
    _IDX_KEY,
    RedisMemoryStore,
)
from engram.backend.agents.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.agents.memory.types import MemoryFilter

TEST_DSN = os.environ.get("ENGRAM_TEST_REDIS_DSN", "").strip()

needs_redis = pytest.mark.skipif(
    not TEST_DSN, reason="ENGRAM_TEST_REDIS_DSN not set; live Redis required"
)


def _trace(content: str = "mem", **kw) -> MemoryTrace:
    """构造测试 trace：thread 分区字段按 worker:{thread} source 形态。"""
    defaults = dict(
        id=uuid.uuid4().hex,
        content=content,
        type=MemoryType.EPISODIC,
        created_at=time.time(),
        strength=0.7,
    )
    defaults.update(kw)
    return MemoryTrace(**defaults)


def _fakeredis_client():
    import fakeredis

    return fakeredis.FakeStrictRedis()


# ── 分区隔离 ─────────────────────────────────────────────────

def test_partition_isolation_between_threads() -> None:
    """不同 thread 的数据互不可见：partition 视图各自只看到自己的记忆。"""
    store = RedisMemoryStore(_fakeredis_client())
    t1 = _trace("thread-1 memory", source="worker:thread-aaa:1")
    t2 = _trace("thread-2 memory", source="worker:thread-bbb:1")
    store.add(t1)
    store.add(t2)

    part1 = store.partition("default-user", "thread-aaa")
    part2 = store.partition("default-user", "thread-bbb")
    assert [t.content for t in part1.list()] == ["thread-1 memory"]
    assert [t.content for t in part2.list()] == ["thread-2 memory"]
    # 键按 thread 分区（键名含 thread id）
    ids1 = {t.id for t in part1.list()}
    assert store._client.exists("engram:mem:default-user:thread-aaa:" + t1.id)
    assert not store._client.exists("engram:mem:default-user:thread-bbb:" + t1.id)


def test_partition_isolation_between_users() -> None:
    """user 维度分区：不同 user 的 thread 同名也不互通。"""
    store = RedisMemoryStore(_fakeredis_client())
    a = _trace("alice mem", source="worker:t1:1", metadata={"user_id": "alice"})
    b = _trace("bob mem", source="worker:t1:1", metadata={"user_id": "bob"})
    store.add(a)
    store.add(b)
    alice = store.partition("alice", "t1")
    bob = store.partition("bob", "t1")
    assert [t.content for t in alice.list()] == ["alice mem"]
    assert [t.content for t in bob.list()] == ["bob mem"]


# ── TTL 语义 ─────────────────────────────────────────────────

def test_ttl_expiry_key_vanishes() -> None:
    """到期键消失：短 TTL 写入 → 过期后 get 返 None、键不存在、索引惰性清理。"""
    client = _fakeredis_client()
    store = RedisMemoryStore(client, ttl_seconds=1)
    trace = _trace("hot memory", source="worker:thread-ttl:1")
    store.add(trace)
    key = "engram:mem:default-user:thread-ttl:" + trace.id
    assert client.exists(key)
    ttl_before = client.ttl(key)
    assert 0 < ttl_before <= 1

    time.sleep(1.2)  # 等过期（fakeredis 按真实时钟过期）
    assert not client.exists(key)  # 键消失
    assert store.get(trace.id) is None  # 读取 = 不存在
    assert trace.id not in client.hkeys(_IDX_KEY)  # 索引残留被惰性清理
    assert store.partition("default-user", "thread-ttl").list() == []


def test_read_refreshes_ttl() -> None:
    """读命中刷新 TTL——常被检索的记忆保持热（热层核心语义）。"""
    client = _fakeredis_client()
    store = RedisMemoryStore(client, ttl_seconds=2)
    trace = _trace("refreshed", source="worker:thread-hot:1")
    store.add(trace)
    key = "engram:mem:default-user:thread-hot:" + trace.id

    time.sleep(1.1)
    assert store.get(trace.id) is not None  # 读命中
    assert client.ttl(key) > 1  # TTL 被刷新回满
    time.sleep(1.1)  # 若无刷新此处已过期
    assert client.exists(key)  # 仍在（刷新生效）


def test_no_ttl_permanent() -> None:
    """ttl_seconds=None → 不淘汰（永驻热层）。"""
    client = _fakeredis_client()
    store = RedisMemoryStore(client, ttl_seconds=None)
    trace = _trace("permanent", source="worker:thread-p:1")
    store.add(trace)
    assert client.ttl("engram:mem:default-user:thread-p:" + trace.id) == -1


# ── 协议语义（与 MarkdownFileStore 对齐） ──────────────────────

def test_add_conflict_and_crud_roundtrip() -> None:
    store = RedisMemoryStore(_fakeredis_client())
    trace = _trace("roundtrip", source="worker:thread-c:1")
    store.add(trace)
    with pytest.raises(MemoryConflictError):
        store.add(trace)

    got = store.get(trace.id)
    assert got is not None and got.content == "roundtrip"
    # roundtrip 保真：frozen 字段还原
    assert got.type == MemoryType.EPISODIC
    assert got.strength == trace.strength

    strengthened = got.with_strength(0.9, time.time())
    store.update(strengthened)
    assert store.get(trace.id).strength == 0.9

    with pytest.raises(MemoryNotFoundError):
        store.update(_trace("ghost", id=uuid.uuid4().hex, source="worker:thread-c:1"))

    store.remove(trace.id)
    assert store.get(trace.id) is None
    store.remove(trace.id)  # 幂等


def test_list_by_type_and_filter() -> None:
    store = RedisMemoryStore(_fakeredis_client())
    e = _trace("epi", type=MemoryType.EPISODIC, source="worker:thread-l:1")
    s = _trace("sem", type=MemoryType.SEMANTIC, source="worker:thread-l:1")
    store.add(e)
    store.add(s)
    assert [t.id for t in store.list_by_type(MemoryType.EPISODIC)] == [e.id]
    # min_strength 过滤
    flt = MemoryFilter(min_strength=0.8)
    assert all(t.strength >= 0.8 for t in store.list_by_filter(flt))
    assert len(store.list_all()) == 2


# ── live（真 Redis，CI service / docker 本地） ─────────────────

@needs_redis
def test_live_redis_roundtrip_and_ttl() -> None:
    """真 Redis：分区隔离 + TTL 到期消失 + 读刷新（redis-cli 同款语义）。"""
    import redis

    client = redis.Redis.from_url(TEST_DSN, decode_responses=False)
    store = RedisMemoryStore(client, ttl_seconds=2)
    t_a = _trace("live-a", source="worker:thread-live-a:1")
    t_b = _trace("live-b", source="worker:thread-live-b:1")
    store.add(t_a)
    store.add(t_b)

    assert [t.content for t in store.partition("default-user", "thread-live-a").list()] == ["live-a"]
    key = "engram:mem:default-user:thread-live-a:" + t_a.id
    assert 0 < client.ttl(key) <= 2  # redis-cli 可见 TTL 倒计时
    assert store.get(t_a.id) is not None  # 刷新
    time.sleep(2.2)
    assert not client.exists(key)  # 到期消失
    assert store.get(t_a.id) is None
    store.remove(t_b.id)
    assert store.get(t_b.id) is None
