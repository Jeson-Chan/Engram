"""记忆用户与线程隔离回归 — E2E 缺陷 C/D（runtime-hardening）。

E2E 现场：
- C：user_id=alice 的会话写入秘密后，user_id=bob 的新会话能召回该秘密
  （MemoryQuery 只有 text；retriever 扫全局 list_all()；写入无 user 归属）。
- D：Redis key `engram:mem:default:unknown:<id>`、trace source
  `worker:unknown`、PG thread_id=unknown（middleware 读
  getattr(runtime, "config") 永远 None）。

修复验证：
- MemoryQuery.user_id 过滤召回（bob 看不到 alice；default 查询仍读旧数据）
- worker encode/consolidate 归属 metadata（user_id/thread_id）
- middleware 经 langgraph get_config() 取真实 thread_id/user_id
- Redis 分区键（fakeredis 真实客户端）包含正确 user/thread
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables.config import var_child_runnable_config

from engram.backend.agents.memory.schema import MemoryTrace, MemoryType
from engram.backend.agents.memory.strategies.default.decay import EbbinghausDecayPolicy
from engram.backend.agents.memory.strategies.default.manager import (
    DefaultMemoryManager,
    set_turn_id,
)
from engram.backend.agents.memory.strategies.default.retriever import HybridRetriever
from engram.backend.agents.memory.types import MemoryQuery
from engram.backend.agents.middlewares.memory_consolidation_middleware import (
    MemoryConsolidationMiddleware,
)
from engram.backend.agents.middlewares.memory_recall_middleware import MemoryMiddleware
from engram.backend.agents.memory.worker import MemoryTask, MemoryWorker


class _DictStore:
    """最小 MemoryStore（内存 dict），隔离测试不依赖任何后端。"""

    def __init__(self) -> None:
        self._traces: dict[str, MemoryTrace] = {}

    def add(self, trace: MemoryTrace) -> None:
        if trace.id in self._traces:
            from engram.backend.agents.memory.exceptions import MemoryConflictError

            raise MemoryConflictError("dup: " + trace.id, old_id=trace.id, new_id=trace.id)
        self._traces[trace.id] = trace

    def get(self, trace_id: str) -> MemoryTrace | None:
        return self._traces.get(trace_id)

    def update(self, trace: MemoryTrace) -> None:
        self._traces[trace.id] = trace

    def batch_update(self, traces: list[MemoryTrace]) -> None:
        for t in traces:
            self.update(t)

    def remove(self, trace_id: str) -> None:
        self._traces.pop(trace_id, None)

    def list_by_type(self, type: MemoryType) -> list[MemoryTrace]:
        return [t for t in self._traces.values() if t.type == type]

    def list_all(self) -> list[MemoryTrace]:
        return list(self._traces.values())


def _trace(content: str, *, user_id: str | None, thread_id: str | None, **kw) -> MemoryTrace:
    metadata: dict = dict(kw.pop("metadata", {}))
    if user_id is not None:
        metadata["user_id"] = user_id
    if thread_id is not None:
        metadata["thread_id"] = thread_id
    base = dict(
        id=kw.pop("id", "id-" + content[:6]),
        content=content,
        type=kw.pop("type", MemoryType.EPISODIC),
        strength=0.9,
        created_at=1_700_000_000.0,
    )
    base.update(kw)
    return MemoryTrace(metadata=metadata, **base)


class TestRecallUserIsolation:
    """缺陷 C：不同用户不互相召回 + 旧 default 数据仍可读。"""

    def _retriever(self, store: _DictStore) -> HybridRetriever:
        return HybridRetriever(store, EbbinghausDecayPolicy())

    def test_bob_cannot_recall_alice_secret(self):
        store = _DictStore()
        store.add(_trace("ALICE-SECRET-777 秘密", user_id="alice", thread_id="ta"))
        store.add(_trace("bob 的普通备忘", user_id="bob", thread_id="tb"))
        retriever = self._retriever(store)

        results = retriever.retrieve(MemoryQuery(text="secret 秘密", user_id="bob"))
        assert all(
            (r.trace.metadata.get("user_id") or "default-user") == "bob" for r in results
        )
        assert "ALICE-SECRET-777" not in " ".join(r.trace.content for r in results)

        # alice 自己能召回
        results_alice = retriever.retrieve(MemoryQuery(text="secret 秘密", user_id="alice"))
        assert any("ALICE-SECRET-777" in r.trace.content for r in results_alice)

    def test_old_default_data_still_readable(self):
        store = _DictStore()
        store.add(_trace("legacy memory without user metadata", user_id=None, thread_id=None))
        retriever = self._retriever(store)

        results = retriever.retrieve(MemoryQuery(text="legacy memory", user_id="default-user"))
        assert any("legacy" in r.trace.content for r in results)

    def test_no_user_filter_keeps_legacy_behavior(self):
        store = _DictStore()
        store.add(_trace("alice 记忆", user_id="alice", thread_id="ta"))
        store.add(_trace("bob 记忆", user_id="bob", thread_id="tb"))
        retriever = self._retriever(store)

        results = retriever.retrieve(MemoryQuery(text="记忆"))
        assert len(results) == 2  # user_id=None：不按用户过滤（兼容）


class TestWorkerOwnership:
    """缺陷 C：encode 归属 metadata + 用户化的 trace id。"""

    def _worker(self, store: _DictStore, llm_response: str) -> MemoryWorker:
        manager = DefaultMemoryManager(store=store)
        return MemoryWorker(manager, llm=_FakeLLM(llm_response))

    def test_encode_carries_user_and_thread(self):
        store = _DictStore()
        worker = self._worker(
            store,
            '[{"content": "bob 喜欢围棋", "type": "episodic", "importance": 0.8}]',
        )
        task = MemoryTask(thread_id="thread-bob-1", messages=[], turn_count=3, user_id="bob")
        worker._extract_and_encode(task)

        traces = store.list_all()
        assert len(traces) == 1
        assert traces[0].metadata["user_id"] == "bob"
        assert traces[0].metadata["thread_id"] == "thread-bob-1"
        assert traces[0].source == "worker:thread-bob-1"

    def test_same_content_different_users_get_distinct_ids(self):
        """同内容不同用户 → 不同 trace id（不互相覆盖归属）。"""
        store = _DictStore()
        worker = self._worker(
            store, '[{"content": "喜欢围棋", "type": "episodic", "importance": 0.8}]',
        )
        worker._extract_and_encode(
            MemoryTask(thread_id="ta", messages=[], turn_count=1, user_id="alice")
        )
        worker._extract_and_encode(
            MemoryTask(thread_id="tb", messages=[], turn_count=1, user_id="bob")
        )
        assert len(store.list_all()) == 2  # 两条独立 trace

    def test_task_without_user_keeps_legacy(self):
        store = _DictStore()
        worker = self._worker(
            store, '[{"content": "legacy", "type": "episodic", "importance": 0.5}]',
        )
        worker._extract_and_encode(MemoryTask(thread_id="t1", messages=[], turn_count=1))
        trace = store.list_all()[0]
        assert "user_id" not in trace.metadata  # 旧路径：不带 user_id（default 分区）


class TestConsolidateOwnership:
    def test_consolidate_inherits_user_and_thread(self):
        store = _DictStore()
        manager = DefaultMemoryManager(store=store)
        set_turn_id("worker:t9:5")
        try:
            t1 = manager.encode(
                "记忆一", MemoryType.EPISODIC, source="worker:t9",
                metadata={"user_id": "alice", "thread_id": "t9"},
            )
            t2 = manager.encode(
                "记忆二", MemoryType.EPISODIC, source="worker:t9",
                metadata={"user_id": "alice", "thread_id": "t9"},
            )
            merged = manager.consolidate([t1.id, t2.id], "合并知识", user_id="alice")
        finally:
            set_turn_id(None)

        assert merged.metadata["user_id"] == "alice"
        assert merged.metadata["thread_id"] == "t9"
        assert merged.metadata["consolidated_from"] == [t1.id, t2.id]

    def test_consolidate_infers_user_from_sources(self):
        store = _DictStore()
        manager = DefaultMemoryManager(store=store)
        t1 = manager.encode("一", MemoryType.EPISODIC, metadata={"user_id": "bob"})
        t2 = manager.encode("二", MemoryType.EPISODIC, metadata={"user_id": "bob"})
        merged = manager.consolidate([t1.id, t2.id], "bob 的合并")
        assert merged.metadata["user_id"] == "bob"


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    def invoke(self, prompt: str) -> Any:
        return type("Resp", (), {"content": self._response})()


class _RecordingRetriever:
    def __init__(self) -> None:
        self.queries: list[MemoryQuery] = []

    def retrieve(self, query: MemoryQuery) -> list:
        self.queries.append(query)
        return []


class _RecordingWorker:
    def __init__(self) -> None:
        self.tasks: list[MemoryTask] = []

    def submit(self, task: MemoryTask) -> None:
        self.tasks.append(task)


async def _run_with_config(config: dict, coro_fn):
    """在真实 langgraph runnable config 上下文里 await 协程（get_config 可用）。

    contextvar 必须在 await 期间保持 set——协程在重置后的上下文里执行
    会读不到 config。
    """
    token = var_child_runnable_config.set(config)
    try:
        return await coro_fn()
    finally:
        var_child_runnable_config.reset(token)


class TestMiddlewareConfigPlumbing:
    """缺陷 D：middleware 从 get_config() 取真实 thread_id/user_id。"""

    def _state(self, n_messages: int = 2) -> dict:
        return {
            "messages": [HumanMessage(content="问题")] + [
                AIMessage(content="答") for _ in range(n_messages - 1)
            ],
        }

    @pytest.mark.anyio
    async def test_recall_passes_user_id(self):
        retriever = _RecordingRetriever()
        mw = MemoryMiddleware(
            type("P", (), {"retriever": lambda self: retriever})(),
        )
        config = {"configurable": {"thread_id": "real-thread-1", "user_id": "alice"}}
        await _run_with_config(config, lambda: mw.abefore_model(self._state(), runtime=None))
        assert retriever.queries
        assert retriever.queries[0].user_id == "alice"

    @pytest.mark.anyio
    async def test_recall_turn_id_uses_real_thread(self):
        retriever = _RecordingRetriever()
        provider = type("P", (), {"retriever": lambda self: retriever})()
        mw = MemoryMiddleware(provider)
        captured = {}

        from engram.backend.agents.middlewares import memory_recall_middleware as rmw_mod

        original_set = rmw_mod.set_turn_id

        def spy(turn_id):
            if turn_id is not None and "turn_id" not in captured:
                captured["turn_id"] = turn_id  # 只记录注入的值（忽略清除 None）
            original_set(turn_id)

        rmw_mod.set_turn_id = spy
        try:
            config = {"configurable": {"thread_id": "real-thread-42", "user_id": "alice"}}
            await _run_with_config(config, lambda: mw.abefore_model(self._state(), runtime=None))
        finally:
            rmw_mod.set_turn_id = original_set
            set_turn_id(None)
        # 真实 thread_id，不再是 unknown（E2E 缺陷 D）
        assert captured["turn_id"].startswith("real-thread-42:turn:")

    @pytest.mark.anyio
    async def test_recall_without_config_falls_back(self):
        retriever = _RecordingRetriever()
        mw = MemoryMiddleware(
            type("P", (), {"retriever": lambda self: retriever})(),
        )
        # 不设 config 上下文（get_config 抛 RuntimeError → None 路径）
        await mw.abefore_model(self._state(), runtime=None)
        assert retriever.queries[0].user_id is None

    @pytest.mark.anyio
    async def test_consolidation_task_carries_thread_and_user(self):
        worker = _RecordingWorker()
        mw = MemoryConsolidationMiddleware(worker, trigger_every_n_turns=1)
        state = self._state(1)  # 1 个 user turn → 触发
        config = {"configurable": {"thread_id": "real-thread-7", "user_id": "bob"}}
        await _run_with_config(config, lambda: mw.aafter_model(state, runtime=None))
        assert worker.tasks
        task = worker.tasks[0]
        assert task.thread_id == "real-thread-7"
        assert task.user_id == "bob"
        assert task.turn_count == 1

    @pytest.mark.anyio
    async def test_consolidation_with_real_runtime_object(self):
        """真实 langgraph Runtime 对象（E2E 缺陷 D 复现条件）。

        旧代码 getattr(runtime, "config") 在真实 Runtime 上永远 None 且
        state 无 thread_id → 归属 unknown；新代码走 get_config()。
        """
        from langgraph.runtime import Runtime

        worker = _RecordingWorker()
        mw = MemoryConsolidationMiddleware(worker, trigger_every_n_turns=1)
        state = {"messages": [HumanMessage(content="q")]}  # state 无 thread_id
        config = {"configurable": {"thread_id": "real-thread-9", "user_id": "alice"}}
        await _run_with_config(config, lambda: mw.aafter_model(state, runtime=Runtime()))
        assert worker.tasks[0].thread_id == "real-thread-9"  # 不再 unknown
        assert worker.tasks[0].user_id == "alice"

    @pytest.mark.anyio
    async def test_consolidation_without_config_falls_back_state(self):
        worker = _RecordingWorker()
        mw = MemoryConsolidationMiddleware(worker, trigger_every_n_turns=1)
        state = {"messages": [HumanMessage(content="q")], "thread_id": "state-thread"}
        await mw.aafter_model(state, runtime=None)
        assert worker.tasks[0].thread_id == "state-thread"
        assert worker.tasks[0].user_id is None


class TestRedisPartitionKeys:
    """缺陷 D：Redis 分区键包含正确 user/thread（fakeredis 真实客户端）。"""

    def test_partition_key_uses_trace_metadata(self):
        import fakeredis

        from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore

        client = fakeredis.FakeStrictRedis(decode_responses=True)
        store = RedisMemoryStore(client)

        set_turn_id("worker:real-thread-5:2")
        try:
            trace = MemoryTrace(
                id="trace-1",
                content="归属正确的记忆",
                type=MemoryType.EPISODIC,
                strength=0.8,
                created_at=1_700_000_000.0,
                source="worker:real-thread-5",
                metadata={"user_id": "alice", "thread_id": "real-thread-5"},
            )
            store.add(trace)
        finally:
            set_turn_id(None)

        keys = [k for k in client.keys("*") if k.startswith("engram:mem:")]
        assert keys, "应有 engram:mem: 分区键"
        # 分区键格式 engram:mem:<user>:<thread>:<id>，不再有 unknown
        assert any(":alice:real-thread-5:trace-1" in k for k in keys)
        assert not any(":unknown:" in k for k in client.keys("*"))

    def test_old_trace_without_metadata_lands_default(self):
        import fakeredis

        from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore

        client = fakeredis.FakeStrictRedis(decode_responses=True)
        store = RedisMemoryStore(client)
        trace = MemoryTrace(
            id="trace-old",
            content="旧数据",
            type=MemoryType.EPISODIC,
            strength=0.5,
            created_at=1_700_000_000.0,
        )
        store.add(trace)
        keys = [k for k in client.keys("*") if k.startswith("engram:mem:")]
        assert any(":default-user:default:trace-old" in k for k in keys)


class TestEndToEndIsolation:
    """C 端到端：alice 写入 → bob 召回不可见（真实 worker + retriever）。"""

    def test_alice_secret_invisible_to_bob(self):
        store = _DictStore()
        manager = DefaultMemoryManager(store=store)
        worker = MemoryWorker(
            manager, _FakeLLM('[{"content": "ALICE-SECRET-777", "type": "episodic", "importance": 0.9}]'),
        )

        # alice 会话触发巩固任务（真实 worker 抽取路径）
        worker._extract_and_encode(
            MemoryTask(thread_id="alice-thread", messages=[], turn_count=1, user_id="alice")
        )
        # 索引在 trace 写入后冷启动建（模拟重启后的真实 retriever）
        retriever = HybridRetriever(store, EbbinghausDecayPolicy())

        # bob 发起召回（同款 middleware 查询构造：user_id 来自 config）
        results = retriever.retrieve(MemoryQuery(text="ALICE-SECRET-777", user_id="bob"))
        assert results == []

        # alice 能召回自己的秘密
        results = retriever.retrieve(MemoryQuery(text="ALICE-SECRET-777", user_id="alice"))
        assert any("ALICE-SECRET-777" in r.trace.content for r in results)
