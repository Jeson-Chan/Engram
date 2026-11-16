"""Memory bootstrap lifecycle — get/reset/shutdown/set + 反射加载 + journal 注入。

承接 `design_docs/53-memory-l4-middleware-bootstrap.md` §4 Step 2。

lifecycle 4 函数（参照 deer-flow SandboxProvider 模式）：
- get_memory_provider(): 懒加载 + 双检锁 + 反射 config.use
- reset_memory_provider(): 清缓存不关（测试用）
- shutdown_memory_provider(): 关 + 清（hasattr duck-type 委托 store/retriever）
- set_memory_provider(p): 注入（测试用）

_load_memory_provider: 调 build_default_provider(L3 完整版) + journal 注入。
_wrap_store: 装饰器模式，5B 增量索引触发（Batch 3 加）。

INVARIANT：
- 懒加载双检锁：get_memory_provider 线程安全
- shutdown duck-type：hasattr(provider, "shutdown") 委托 store/retriever
- config.use="" 返 None（记忆禁用）
- import 防火墙：bootstrap.py 不 import app
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from engram.backend.agents.memory.config import get_memory_config

# E2E 缺陷 E：StreamConsolidationQueue/Consumer 此前在 _build_worker 函数内
# 局部导入，而 _StreamModeWorker.__init__（同类方法）在模块全局作用域查
# 名 → 必然 NameError → 被吞掉后静默降级为进程内队列（重启丢巩固任务）。
# 修复：提升到模块级导入，_StreamModeWorker 直接引用。
from engram.backend.agents.memory.stream_queue import (
    StreamConsolidationConsumer,
    StreamConsolidationQueue,
)

logger = logging.getLogger(__name__)

_provider_lock = threading.Lock()
_memory_provider: Any = None


def get_memory_provider() -> Any:
    """懒加载 + 双检锁 + 反射 config.use。None 时返 None（记忆禁用）。

    第一次检查无锁（快速路径），第二次检查有锁（防并发）。
    """
    global _memory_provider
    if _memory_provider is not None:
        return _memory_provider
    with _provider_lock:
        if _memory_provider is not None:
            return _memory_provider
        config = get_memory_config()
        if not config.use:
            return None  # 记忆禁用
        provider = _load_memory_provider(config)
        _memory_provider = provider
        return provider


def reset_memory_provider() -> None:
    """清缓存不关（测试用）。"""
    global _memory_provider
    with _provider_lock:
        _memory_provider = None


def shutdown_memory_provider() -> None:
    """关 + 清（hasattr duck-type 委托 store/retriever）。"""
    global _memory_provider
    with _provider_lock:
        if _memory_provider is not None:
            if hasattr(_memory_provider, "shutdown"):
                _memory_provider.shutdown()
            _memory_provider = None


def set_memory_provider(provider: Any) -> None:
    """注入（测试用）。"""
    global _memory_provider
    with _provider_lock:
        _memory_provider = provider


# ---------------------------------------------------------------------------
# L5 worker lifecycle（块 C3）
# ---------------------------------------------------------------------------
_worker_lock = threading.Lock()
_memory_worker: Any = None


def start_memory_worker(manager: Any, llm: Any) -> Any:
    """启动 memory worker。返 worker 实例（submit 接口同构）。

    两种模式（issue 08）：
    - Redis 配置（config.redis_url）→ Stream 模式：本进程内起轻量
      消费线程（Web 进程自含消费能力，同时 submit 走 XADD 持久化——
      Web 重启事件不丢；独立 worker 进程见 consolidation_worker.py，
      可水平加消费而不改代码）
    - 无 Redis → 进程内 queue.Queue + 守护线程（原路径不变）

    幂等：已启动则返既有实例。
    LLM 注入：调用方传 llm（避免 worker 反向依赖 app）。
    """
    global _memory_worker
    if _memory_worker is not None:
        return _memory_worker
    with _worker_lock:
        if _memory_worker is not None:
            return _memory_worker
        worker = _build_worker(manager, llm)
        worker.start()
        _memory_worker = worker
        return worker


def _build_worker(manager: Any, llm: Any) -> Any:
    """按配置选 worker 形态：Stream 队列（Redis）或进程内 Queue。

    两者 submit/shutdown 同构（duck-type），调用方无感。
    """
    config = get_memory_config()
    if config.redis_url:
        try:
            import redis

            client = redis.Redis.from_url(
                config.redis_url, decode_responses=True,
                socket_connect_timeout=5,
            )
            return _StreamModeWorker(client, manager, llm)
        except Exception as exc:
            # 显式降级（可见告警，启动不阻断）：只有 Redis 真正连不上才走这里；
            # 巩固事件退回进程内队列，进程重启即丢（Stream 持久化语义失效）。
            logger.warning(
                "stream worker unavailable (%s): consolidation falls back to the "
                "in-process queue -- events will NOT survive a restart; check "
                "ENGRAM_REDIS_URL / Redis availability",
                exc,
            )
    from engram.backend.agents.memory.worker import MemoryWorker

    return MemoryWorker(manager=manager, llm=llm)


class _StreamModeWorker:
    """Stream 模式的进程内 worker 包装：submit→XADD + 消费线程消费本组。

    与 MemoryWorker 同构（start/shutdown/submit），bootstrap 调用方无感。
    消费循环独立线程，run_forever 阻塞特性在线程里天然满足。
    """

    def __init__(self, client: Any, manager: Any, llm: Any) -> None:
        from engram.backend.agents.memory.worker import MemoryWorker

        self._queue = StreamConsolidationQueue(client)
        self._processor = MemoryWorker(manager=manager, llm=llm)  # 只用 _process
        import threading

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._consumer = StreamConsolidationConsumer(
            client,
            handler=self._processor._process,
            consumer_name="web-inline",
        )

    def submit(self, task: Any) -> None:
        self._queue.submit(task)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._consumer.run_forever, name="memory-stream-worker", daemon=True,
        )
        self._thread.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._consumer.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None


def shutdown_memory_worker(timeout: float = 5.0) -> None:
    """drain + 关闭 worker。"""
    global _memory_worker
    with _worker_lock:
        if _memory_worker is None:
            return
        _memory_worker.shutdown(timeout=timeout)
        _memory_worker = None


def get_memory_worker() -> Any:
    """取当前 worker 实例（可能为 None）。"""
    with _worker_lock:
        return _memory_worker


def _load_memory_provider(config: Any) -> Any:
    """反射加载 + build_default_provider + journal 注入。

    L3 完整版：build_default_provider(store/retriever 从 config 实例化)。
    journal 注入：_make_journal_callback（RunJournal 可用时 lambda，不可用时 None）。
    _wrap_store（5B 增量索引）在 Batch 3 加。
    """
    from engram.backend.agents.memory.strategies.default.strategy import (
        build_default_provider,
    )

    journal = _make_journal_callback()
    provider = build_default_provider(journal=journal)
    _wrap_store(provider.store(), provider.retriever())  # 5B 增量索引触发
    return provider


def _make_journal_callback() -> Any:
    """Layer 4 注入 RunJournal（L2 manager emit memory.* 事件）。

    RunJournal 可用时返 lambda（调 journal.append(event, payload)）；
    不可用时返 None（不发事件）。
    """
    try:
        from engram.backend.agents.journal import get_run_journal

        journal = get_run_journal()
        if journal is None:
            return None
        return lambda event, payload: journal.append(event, payload)
    except Exception as exc:
        logger.debug("RunJournal unavailable, memory journal events disabled: %s", exc)
        return None


def _wrap_store(store: Any, retriever: Any) -> None:
    """装饰器模式：包装 store.add/update/batch_update/remove 后调 retriever.on_trace_*。

    5B 增量索引触发（50 §6.5）：store 变更后 retriever 索引同步更新。
    运行时方法替换，不改 store 类。
    """
    original_add = store.add
    original_update = store.update
    original_batch_update = store.batch_update
    original_remove = store.remove

    def wrapped_add(trace: Any) -> None:
        original_add(trace)
        retriever.on_trace_added(trace)

    def wrapped_update(trace: Any) -> None:
        original_update(trace)
        retriever.on_trace_updated(trace)

    def wrapped_batch_update(traces: list) -> None:
        original_batch_update(traces)
        for t in traces:
            retriever.on_trace_updated(t)

    def wrapped_remove(trace_id: str) -> None:
        original_remove(trace_id)
        retriever.on_trace_removed(trace_id)

    store.add = wrapped_add
    store.update = wrapped_update
    store.batch_update = wrapped_batch_update
    store.remove = wrapped_remove
