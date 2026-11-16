"""Redis Stream 巩固 worker 回归 — E2E 缺陷 E（runtime-hardening）。

E2E 现场：配置 Redis 时每次启动都打印
`stream worker unavailable (name 'StreamConsolidationQueue' is not defined);
falling back to in-process queue` —— StreamConsolidationQueue/Consumer 在
`_build_worker` 函数内局部导入，而 `_StreamModeWorker.__init__` 在模块全局
作用域查名 → 必然 NameError → 巩固事件退回进程内队列，重启即丢。

修复验证：
- fakeredis 下 `_build_worker` 返回 `_StreamModeWorker`（Stream 模式）
- XADD → 消费组读取 → 处理 → XACK 全链路可用
- MemoryTask.user_id 经 Stream 序列化往返不丢（E2E 缺陷 C 的 Stream 路径）
- 降级只在 Redis 真正不可用时发生，且产生 warning（不静默）
"""

from __future__ import annotations

import logging

import pytest

from engram.backend.agents.memory import bootstrap as mem_bootstrap
from engram.backend.agents.memory.bootstrap import _build_worker
from engram.backend.agents.memory.stream_queue import (
    StreamConsolidationConsumer,
    StreamConsolidationQueue,
)
from engram.backend.agents.memory.worker import MemoryTask, MemoryWorker


@pytest.fixture()
def redis_config(monkeypatch, tmp_path):
    """config.redis_url 非空 + redis.Redis.from_url → fakeredis 客户端。"""
    import fakeredis

    client = fakeredis.FakeStrictRedis(decode_responses=True)

    class _FakeFromUrl:
        @staticmethod
        def from_url(url, **kwargs):
            return client

    import redis as redis_mod

    monkeypatch.setattr(redis_mod.Redis, "from_url", _FakeFromUrl.from_url)

    class _Cfg:
        redis_url = "redis://localhost:6379/9"
        use = "default"

    monkeypatch.setattr(mem_bootstrap, "get_memory_config", lambda: _Cfg())
    return client


class TestBuildWorkerStreamMode:
    def test_redis_config_builds_stream_worker(self, redis_config):
        """缺陷 E 回归：Redis 配置下 _build_worker 返回 Stream 模式。"""
        worker = _build_worker(manager=object(), llm=object())
        assert isinstance(worker, mem_bootstrap._StreamModeWorker)

    def test_no_redis_builds_inprocess_worker(self, monkeypatch):
        class _Cfg:
            redis_url = ""
            use = "default"

        monkeypatch.setattr(mem_bootstrap, "get_memory_config", lambda: _Cfg())
        worker = _build_worker(manager=object(), llm=object())
        assert isinstance(worker, MemoryWorker)

    def test_redis_failure_degrades_visibly(self, redis_config, monkeypatch, caplog):
        """降级只在 Redis 真连不上时发生，且产生可见 warning。"""
        import redis as redis_mod

        def _boom(url, **kwargs):
            raise ConnectionError("redis unreachable")

        monkeypatch.setattr(redis_mod.Redis, "from_url", _boom)
        with caplog.at_level(logging.WARNING):
            worker = _build_worker(manager=object(), llm=object())
        assert isinstance(worker, MemoryWorker)  # 显式降级
        assert any("in-process queue" in r.message for r in caplog.records)


class TestStreamRoundtrip:
    def test_xadd_consume_ack_roundtrip(self, redis_config):
        """XADD → 消费组读取 → 处理 → ack；处理后 PEL 清空。"""
        handled: list[MemoryTask] = []

        def handler(task: MemoryTask) -> None:
            handled.append(task)

        queue = StreamConsolidationQueue(redis_config)
        consumer = StreamConsolidationConsumer(
            redis_config, handler=handler, consumer_name="test-c1", block_ms=1,
        )

        from langchain_core.messages import HumanMessage

        queue.submit(MemoryTask(
            thread_id="thread-rt", messages=[HumanMessage(content="巩固这轮")],
            turn_count=4, user_id="alice",
        ))

        processed = consumer.consume_once()
        assert processed >= 1
        assert len(handled) == 1
        task = handled[0]
        assert task.thread_id == "thread-rt"
        assert task.turn_count == 4
        assert task.user_id == "alice"  # user_id 经 Stream 往返不丢（缺陷 C）
        assert task.messages[0].content == "巩固这轮"
        # 处理成功 → ack → pending 清空
        assert consumer.pending_count() == 0

    def test_failed_handler_stays_pending(self, redis_config):
        """handler 失败不 ack → 留 PEL（at-least-once 重放语义）。"""

        def handler(task: MemoryTask) -> None:
            raise RuntimeError("boom")

        queue = StreamConsolidationQueue(redis_config)
        consumer = StreamConsolidationConsumer(
            redis_config, handler=handler, consumer_name="test-c2", block_ms=1,
        )
        from langchain_core.messages import HumanMessage

        queue.submit(MemoryTask(
            thread_id="t", messages=[HumanMessage(content="x")], turn_count=1,
        ))
        consumer.consume_once()
        assert consumer.pending_count() == 1  # 未 ack，留 PEL

    def test_start_worker_stream_mode_submits_and_consumes(self, redis_config):
        """端到端：_StreamModeWorker.submit → XADD；consumer 消费到。"""
        from langchain_core.messages import HumanMessage

        worker = _build_worker(manager=object(), llm=object())
        assert isinstance(worker, mem_bootstrap._StreamModeWorker)

        seen: list[MemoryTask] = []
        consumer = StreamConsolidationConsumer(
            redis_config, handler=seen.append, consumer_name="test-c3", block_ms=1,
        )
        worker.submit(MemoryTask(
            thread_id="thread-e2e",
            messages=[HumanMessage(content="stream 事件的归属")],
            turn_count=2, user_id="bob",
        ))
        consumer.consume_once()
        assert seen and seen[0].user_id == "bob"
        assert seen[0].thread_id == "thread-e2e"

