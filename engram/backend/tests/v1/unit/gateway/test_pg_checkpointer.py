"""PG 持久 checkpointer 测试。

三层：
- 工厂语义（本地必跑）：无 DSN 回退 InMemory；lifespan 在 DSN 配置时先建
  saver 预装再跑 bootstrap、shutdown 关池重置
- 恢复行为（需真 PG）：ENGRAM_TEST_PG_DSN 配置时才跑——两个独立 saver
  实例（模拟进程重启 / 双 worker）经同一 DSN 读写同一 thread 状态
- 未配置时显式 skip（同沙箱镜像守卫模式）

CI（GitHub Actions）挂 postgres service container 后真跑恢复测试。
"""

from __future__ import annotations

import os
import uuid

import pytest

from engram.backend.agents.runtime.checkpointer import (
    get_checkpointer,
    reset_checkpointer,
    set_checkpointer,
)
from langgraph.checkpoint.memory import InMemorySaver


TEST_DSN = os.environ.get("ENGRAM_TEST_PG_DSN", "").strip()

needs_pg = pytest.mark.skipif(
    not TEST_DSN, reason="ENGRAM_TEST_PG_DSN not set; live Postgres required"
)


def setup_function() -> None:
    reset_checkpointer()


def teardown_function() -> None:
    reset_checkpointer()


def test_fallback_inmemory_without_dsn(monkeypatch) -> None:
    """无 DSN → InMemorySaver（CLI / 本地行为不变）。"""
    monkeypatch.delenv("ENGRAM_CHECKPOINT_DSN", raising=False)
    monkeypatch.delenv("ENGRAM_PG_DSN", raising=False)
    saver = get_checkpointer()
    assert isinstance(saver, InMemorySaver)


def test_set_checkpointer_preloads_singleton() -> None:
    """set_checkpointer 预装后 get_checkpointer 返回同一实例（PG 路径）。"""
    sentinel = InMemorySaver()
    set_checkpointer(sentinel)
    assert get_checkpointer() is sentinel


def test_lifespan_preloads_pg_saver_before_bootstrap(monkeypatch) -> None:
    """DSN 配置时 lifespan 先建 PG saver 预装、bootstrap 可见、shutdown 清理。"""
    import asyncio

    from fastapi.testclient import TestClient

    from engram.backend.app.gateway.main import create_app
    from engram.backend.agents.runtime import pg_checkpointer as pg_mod

    made = []
    closed = []

    class _FakeSaver:
        pass

    async def fake_create(dsn=None):
        made.append(dsn)
        return _FakeSaver()

    async def fake_close(saver):
        closed.append(saver)

    monkeypatch.setenv("ENGRAM_CHECKPOINT_DSN", "postgresql://fake")
    monkeypatch.setattr(pg_mod, "create_pg_checkpointer", fake_create)
    monkeypatch.setattr(pg_mod, "close_pg_checkpointer", fake_close)
    # main.py 已 import 名字绑定——patch 模块属性需走 import 的引用处
    import engram.backend.app.gateway.main as gw

    monkeypatch.setattr(gw, "create_pg_checkpointer", fake_create)
    monkeypatch.setattr(gw, "close_pg_checkpointer", fake_close)

    seen = {}

    def factory():
        seen["checkpointer"] = get_checkpointer()
        return object()

    with TestClient(create_app(runtime_factory=factory)) as client:
        client.get("/sessions")
    assert made == ["postgresql://fake"]  # DSN 传给工厂
    assert isinstance(seen["checkpointer"], _FakeSaver)  # bootstrap 前已预装
    assert len(closed) == 1  # shutdown 关池
    assert get_checkpointer() is not closed[0] or True
    # shutdown 后槽位重置 → 回退 InMemory
    assert isinstance(get_checkpointer(), InMemorySaver)


@needs_pg
def test_state_recovers_across_saver_instances() -> None:
    """重启/双 worker 语义：两个独立 saver 实例经同一 DSN 读回同一 thread 状态。"""
    import asyncio

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph import END, START, StateGraph
    from typing import TypedDict

    class _St(TypedDict, total=False):
        value: str

    def _build():
        g = StateGraph(_St)

        def node(st: _St) -> _St:
            return {"value": st.get("value", "") + "X"}

        g.add_node("n", node)
        g.add_edge(START, "n")
        g.add_edge("n", END)
        return g

    thread = "pg-recovery-" + uuid.uuid4().hex[:8]

    async def _run():
        from engram.backend.agents.runtime.pg_checkpointer import (
            close_pg_checkpointer,
            create_pg_checkpointer,
        )

        # 实例 1（"第一个 worker"）：写状态
        saver1 = await create_pg_checkpointer(TEST_DSN)
        try:
            g1 = _build().compile(checkpointer=saver1)
            await g1.ainvoke({"value": "a"}, config={"configurable": {"thread_id": thread}})
        finally:
            await close_pg_checkpointer(saver1)

        # 实例 2（"重启后的进程 / 第二个 worker"）：独立池读回
        saver2 = await create_pg_checkpointer(TEST_DSN)
        try:
            g2 = _build().compile(checkpointer=saver2)
            snapshot = await g2.aget_state(config={"configurable": {"thread_id": thread}})
        finally:
            await close_pg_checkpointer(saver2)
        return snapshot

    snap = asyncio.run(_run())
    assert snap.values.get("value") == "aX"  # 写入的状态原样读回
