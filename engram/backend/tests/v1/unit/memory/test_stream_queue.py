"""Redis Stream 巩固队列语义测试 — 消费者组 / at-least-once / 断线续传。

核心演示语义（issue 08 验收）：
- 杀消费者 → 重启 → pending 重放不丢
- 消费者组偏移量续传（重启只取新消息 + 认领孤儿）
- 成功 ack 后不再重投
- 生产者崩溃 → Stream 持久 → 消费者照常消费（Web 重启不丢事件）

fakeredis 支持 xadd/xreadgroup/xack/xpending/xautoclaim（语义级实现），
本地全跑；live 测试（ENGRAM_TEST_REDIS_DSN）在真 redis 复验。
"""

from __future__ import annotations

import os
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from engram.backend.agents.memory.stream_queue import (
    GROUP_NAME,
    STREAM_KEY,
    StreamConsolidationConsumer,
    StreamConsolidationQueue,
)
from engram.backend.agents.memory.worker import MemoryTask

TEST_DSN = os.environ.get("ENGRAM_TEST_REDIS_DSN", "").strip()

needs_redis = pytest.mark.skipif(
    not TEST_DSN, reason="ENGRAM_TEST_REDIS_DSN not set; live Redis required"
)


def _client():
    import fakeredis

    return fakeredis.FakeStrictRedis(decode_responses=True)


def _task(content: str = "hello") -> MemoryTask:
    return MemoryTask(
        thread_id="thread-test",
        messages=[HumanMessage(content=content), AIMessage(content="ack")],
        turn_count=3,
    )


def _drain(consumer: StreamConsolidationConsumer, rounds: int = 3) -> int:
    """非阻塞排干：多轮 consume_once（block=0 场景手动驱动）。"""
    total = 0
    for _ in range(rounds):
        total += consumer.consume_once()
    return total


def _consumer(client, handler, name="c1", **kw):
    kw.setdefault("block_ms", 1)
    kw.setdefault("claim_min_idle_ms", 0)  # 测试立即认领
    return StreamConsolidationConsumer(client, handler, consumer_name=name, **kw)


# ── 基础语义 ─────────────────────────────────────────────────

def test_produce_consume_ack_roundtrip() -> None:
    """XADD → XREADGROUP 消费 → ack；ack 后 pending 归零。"""
    client = _client()
    handled: list[str] = []
    queue = StreamConsolidationQueue(client)
    queue.submit(_task("memory-1"))

    consumer = _consumer(client, lambda t: handled.append(t.messages[0].content))
    processed = consumer.consume_once()
    assert processed == 1
    assert handled == ["memory-1"]
    assert consumer.pending_count() == 0  # ack 了


def test_handler_failure_stays_pending() -> None:
    """处理失败不 ack → 留 PEL（at-least-once 核心）。"""
    client = _client()
    queue = StreamConsolidationQueue(client)
    queue.submit(_task("boom"))

    def failing(task):
        raise RuntimeError("handler failed")

    consumer = _consumer(client, failing)
    consumer.consume_once()  # 读到 + 处理失败（不 ack）
    assert consumer.pending_count() == 1  # 留在 PEL


def test_blocked_read_timeout_is_empty_not_error() -> None:
    """review/smoke 回归：阻塞读客户端超时 = 没有消息，consume_once 不抛错。"""
    import redis as _redis

    class _TimeoutClient:
        def xgroup_create(self, *a, **k):
            pass

        def xreadgroup(self, *a, **k):
            raise _redis.exceptions.TimeoutError("Timeout reading from socket")

        def xautoclaim(self, *a, **k):
            raise _redis.exceptions.TimeoutError("Timeout reading from socket")

    consumer = StreamConsolidationConsumer(
        _TimeoutClient(), lambda t: None, consumer_name="c-timeout",
    )
    assert consumer.consume_once() == 0  # 无消息：干净返回，不是错误

def test_poison_message_acked() -> None:
    """载荷损坏（毒丸）直接 ack，不永久重放。"""
    client = _client()
    client.xadd(STREAM_KEY, {"garbage": "not-a-valid-payload"})
    handled = []
    consumer = _consumer(client, lambda t: handled.append(t))
    processed = consumer.consume_once()
    assert processed == 0  # 毒丸不计处理成功
    assert consumer.pending_count() == 0  # 但被 ack 清掉


def test_messages_serialize_roundtrip() -> None:
    """MemoryTask 经 Stream 序列化往返（HumanMessage/AIMessage 还原）。"""
    client = _client()
    seen: list[MemoryTask] = []
    queue = StreamConsolidationQueue(client)
    queue.submit(_task("roundtrip message"))
    consumer = _consumer(client, seen.append)
    consumer.consume_once()
    assert len(seen) == 1
    task = seen[0]
    assert task.thread_id == "thread-test"
    assert task.turn_count == 3
    assert isinstance(task.messages[0], HumanMessage)
    assert task.messages[0].content == "roundtrip message"
    assert isinstance(task.messages[1], AIMessage)


# ── 核心演示：杀消费者 → 重启 → 重放不丢 ─────────────────────

def test_killed_consumer_replays_pending() -> None:
    """杀消费者（处理失败模拟崩溃）→ 新消费者认领 PEL → 事件重放成功。"""
    client = _client()
    queue = StreamConsolidationQueue(client)
    queue.submit(_task("event-1"))
    queue.submit(_task("event-2"))

    # 第一个消费者：读到但处理失败（模拟崩溃：不 ack）
    def crash(task):
        raise RuntimeError("consumer crashed mid-processing")

    c1 = _consumer(client, crash, name="c1")
    c1.consume_once()
    assert c1.pending_count() == 2  # 两条都进 PEL

    # "重启"：新消费者（新名字）——认领孤儿 + 重放成功
    handled: list[str] = []
    c2 = _consumer(client, lambda t: handled.append(t.messages[0].content), name="c2")
    processed = c2.consume_once()  # reclaim_orphans 先跑
    assert processed == 2
    assert sorted(handled) == ["event-1", "event-2"]
    assert c2.pending_count() == 0  # 重放后 ack 清


def test_offset_resume_new_messages_only() -> None:
    """偏移量续传：重启后 '>' 只取新消息，已 ack 的旧消息不重投。"""
    client = _client()
    queue = StreamConsolidationQueue(client)
    handled: list[str] = []
    c1 = _consumer(client, lambda t: handled.append(t.messages[0].content), name="c1")
    queue.submit(_task("old-1"))
    c1.consume_once()  # 处理 + ack
    assert handled == ["old-1"]

    # "重启"后同组新消费者
    c2 = _consumer(client, lambda t: handled.append(t.messages[0].content), name="c2")
    processed = c2.consume_once()
    assert processed == 0  # 组偏移量已推进——旧消息不重投

    queue.submit(_task("new-1"))
    assert c2.consume_once() == 1
    assert handled == ["old-1", "new-1"]  # 顺序：旧一次 + 新一次


def test_web_restart_events_not_lost() -> None:
    """生产者（Web）重启不丢事件：Stream 持久，消费者晚到照常消费。"""
    client = _client()
    queue = StreamConsolidationQueue(client)
    # Web 阶段：只生产（此时无消费者）
    queue.submit(_task("pre-web-restart"))
    # "Web 重启"（queue 对象丢弃重建——Stream 才是真相）
    queue2 = StreamConsolidationQueue(client)
    queue2.submit(_task("post-restart"))
    # worker 后到
    handled: list[str] = []
    consumer = _consumer(client, lambda t: handled.append(t.messages[0].content))
    assert consumer.consume_once() >= 1
    _drain(consumer, rounds=2)
    assert sorted(handled) == ["post-restart", "pre-web-restart"]


# ── live（真 redis 复验核心语义） ──────────────────────────────

@needs_redis
def test_live_kill_and_replay() -> None:
    """真 redis：崩溃 → 重启 → pending 重放不丢（redis-cli 可见 XLEN/XINFO）。"""
    import redis

    client = redis.Redis.from_url(TEST_DSN, decode_responses=True)
    client.delete(STREAM_KEY)
    queue = StreamConsolidationQueue(client)
    for i in range(3):
        queue.submit(_task("live-event-%d" % i))

    def crash(task):
        raise RuntimeError("crash")

    c1 = _consumer(client, crash, name="live-c1")
    c1.consume_once()
    assert c1.pending_count() == 3

    handled = []
    c2 = _consumer(client, lambda t: handled.append(t.messages[0].content), name="live-c2")
    processed = c2.consume_once()
    assert processed == 3
    assert sorted(handled) == ["live-event-0", "live-event-1", "live-event-2"]
    assert c2.pending_count() == 0
    client.delete(STREAM_KEY)
