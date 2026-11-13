"""Checkpointer 工厂 — LangGraph graph 状态持久化单例。

借鉴 deer-flow runtime/checkpointer/provider.py。默认 InMemorySaver（进程内，
CLI / 测试）；PG 持久形态见 pg_checkpointer.py——网关 lifespan 在 DSN 配置时
先异步建 AsyncPostgresSaver 并 set_checkpointer() 预装，这里 get_checkpointer()
就返回它（进程内单例退役，持久化生效）。

checkpointer 是 create_agent(checkpointer=...) 编译参数，LangGraph 内部处理持久化，
无 hook。thread_id 在 config.configurable 透传，自动按 thread 存取 state。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer

_cp: Checkpointer | None = None


def get_checkpointer() -> Checkpointer:
    """返回全局 checkpointer 单例（预装的 PG saver 或 InMemorySaver）。

    PG 路径：lifespan 已 set_checkpointer(AsyncPostgresSaver) 时直接返回它。
    未预装（本地 CLI / 测试）→ 首次调用创建 InMemorySaver。模式切换重建
    graph 时复用同一单例 + 同一 thread_id，state 跨模式累积保留。
    """
    global _cp
    if _cp is None:
        _cp = InMemorySaver()
    return _cp


def set_checkpointer(saver: Checkpointer) -> None:
    """预装持久 saver（PG）进单例槽位——须在首次 get_checkpointer() 前。"""
    global _cp
    _cp = saver


def reset_checkpointer() -> None:
    """重置单例，强制下次 get_checkpointer() 创建新实例。测试用。"""
    global _cp
    _cp = None
