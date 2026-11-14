"""默认 MemoryProvider 主入口（组合 store + retriever + manager）。

承接 `Hezao-MemDesign-Docs/engram/48-memory-l1-base-layer.md` §4 Step 6.3 骨架
+ `49-memory-l2-default-strategies.md` §4 Step 5。

Layer 1：空骨架，build_default_provider() 返 NotImplementedError 占位。
Layer 2：部分组装 — 接收 store + retriever 参数注入，组装 manager + decay + forget。
Layer 3（本实现）：完整版 — 从 config 实例化 MarkdownFileStore + HybridRetriever，组装 DefaultMemoryProvider。

INVARIANT：
- DefaultMemoryProvider frozen dataclass，三组件构造时注入，运行时不可变
- shutdown duck-type：委托 store/retriever（hasattr 检查）
- store/retriever/journal 由调用方注入（Layer 2 测试 mock，Layer 3 后真实实例）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from engram.backend.agents.memory.config import get_memory_config
from engram.backend.agents.memory.memory_manager import MemoryManager
from engram.backend.agents.memory.memory_provider import MemoryProvider
from engram.backend.agents.memory.memory_store import MemoryStore
from engram.backend.agents.memory.retriever import Retriever
from engram.backend.agents.memory.strategies.default.decay import EbbinghausDecayPolicy
from engram.backend.agents.memory.strategies.default.forget import CompositeForgetPolicy
from engram.backend.agents.memory.strategies.default.manager import DefaultMemoryManager
from engram.backend.agents.memory.strategies.default.retriever import HybridRetriever
from engram.backend.agents.memory.strategies.default.store import MarkdownFileStore


@dataclass(frozen=True)
class DefaultMemoryProvider:
    """默认 MemoryProvider 实现（组合 store + retriever + manager）。

    frozen dataclass，三组件构造时注入，运行时不可变。
    Lifecycle：构造即就绪，shutdown 走 hasattr duck-type（委托给 store/retriever）。
    """

    _store: MemoryStore
    _retriever: Retriever
    _manager: MemoryManager

    def store(self) -> MemoryStore:
        return self._store

    def retriever(self) -> Retriever:
        return self._retriever

    def manager(self) -> MemoryManager:
        return self._manager

    def shutdown(self) -> None:
        """可选 shutdown：委托给 store / retriever（若有）。

        hasattr duck-type：MarkdownFileStore 无 shutdown（纯文件），SQLiteShadowStore 有。
        """
        if hasattr(self._store, "shutdown"):
            self._store.shutdown()
        if hasattr(self._retriever, "shutdown"):
            self._retriever.shutdown()


def build_default_provider(
    *,
    store: MemoryStore | None = None,
    retriever: Retriever | None = None,
    decay_policy: EbbinghausDecayPolicy | None = None,
    forget_policy: CompositeForgetPolicy | None = None,
    journal: Callable[[str, dict], None] | None = None,
) -> MemoryProvider:
    """组装默认 MemoryProvider（Layer 3 完整版）。

    Args:
        store: 持久化后端（None 时从 config 实例化 MarkdownFileStore）
        retriever: 检索后端（None 时从 store + decay_policy 实例化 HybridRetriever）
        decay_policy: 衰减策略（None 时默认 EbbinghausDecayPolicy）
        forget_policy: 遗忘策略（None 时默认 CompositeForgetPolicy）
        journal: 事件回调（traceability B，None 时不发事件；Layer 4 注入 RunJournal）

    Returns:
        DefaultMemoryProvider（组合三组件）

    Layer 3：store/retriever 默认从 config 实例化（Layer 4 bootstrap 调此函数）。
    Layer 4 注入 journal（RunJournal）。
    """
    config = get_memory_config()
    decay = decay_policy or EbbinghausDecayPolicy()
    forget = forget_policy or CompositeForgetPolicy(decay)

    # Redis hot tier (issue 06): config.redis_url non-empty -> RedisMemoryStore
    # (per user/thread partitioned keys + per-trace TTL, expired keys vanish;
    # read hits refresh TTL - hot memories stay hot). Else Markdown truth source.
    if store is None:
    # 分层选配（issue 06/07）：
    # - redis + memory_pg 都配 -> TieredMemoryStore（热 miss 查冷 + 回填，冷先沉淀）
    # - 仅 redis -> RedisMemoryStore；仅 memory_pg -> PostgresMemoryStore
    # - 都无 -> MarkdownFileStore（本地 CLI；冷热齐备时 Markdown 退出运行路径）
        import os

        redis_url = config.redis_url
        pg_dsn = os.environ.get("ENGRAM_MEMORY_PG_DSN", "").strip()
        if redis_url and pg_dsn:
            import redis

            from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore
            from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore
            from engram.backend.agents.memory.adapters.tiered_store import TieredMemoryStore

            hot = RedisMemoryStore(redis.Redis.from_url(
                redis_url, decode_responses=True, socket_connect_timeout=5,
            ))
            cold = PostgresMemoryStore(pg_dsn)
            store = TieredMemoryStore(hot, cold)
        elif redis_url:
            import redis

            from engram.backend.agents.memory.adapters.redis_store import RedisMemoryStore

            store = RedisMemoryStore(redis.Redis.from_url(
                redis_url, decode_responses=True, socket_connect_timeout=5,
            ))
        elif pg_dsn:
            from engram.backend.agents.memory.adapters.pg_store import PostgresMemoryStore

            store = PostgresMemoryStore(pg_dsn)
        else:
            store = MarkdownFileStore(config.storage_path)
    if retriever is None:
        retriever = HybridRetriever(store, decay)

    manager = DefaultMemoryManager(
        store=store,
        decay_policy=decay,
        forget_policy=forget,
        journal=journal,  # traceability B 透传
    )
    return DefaultMemoryProvider(
        _store=store,
        _retriever=retriever,
        _manager=manager,
    )
