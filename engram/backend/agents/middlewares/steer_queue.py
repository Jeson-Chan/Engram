"""SteerQueues — thread 隔离的插话队列（real-steer）。

进程内单例：网关与 TUI 各自持有一份（不跨进程）。运行活跃时客户端经
POST /steer（网关）或直接 put（TUI）入队；SteerMiddleware.before_model
排空注入对话；run 结束（after_agent / 网关流 finally）清理防陈旧注入。

INVARIANT:
- 同一条插话只注入一次（drain 即移除）
- thread 隔离：A 线程的插话不进 B 线程
- 线程安全（网关 worker 线程池 / TUI worker 均可能写入）
"""
from __future__ import annotations

import threading
from collections import deque


class SteerQueues:
    """thread_id → deque[str]。"""

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._queues: dict[str, deque[str]] = {}

    def put(self, thread_id: str, text: str) -> bool:
        """入队一条插话；空文本忽略返 False。"""
        text = (text or "").strip()
        if not text:
            return False
        with self._mu:
            self._queues.setdefault(thread_id, deque()).append(text)
        return True

    def drain(self, thread_id: str) -> list[str]:
        """排空该 thread 的全部待注入插话（按入队顺序）。"""
        with self._mu:
            q = self._queues.pop(thread_id, None)
            return list(q) if q else []

    def clear(self, thread_id: str) -> None:
        """丢弃该 thread 的残留插话（run 结束防陈旧注入）。"""
        with self._mu:
            self._queues.pop(thread_id, None)


_singleton: SteerQueues | None = None
_singleton_mu = threading.Lock()


def get_steer_queues() -> SteerQueues:
    """进程级单例（网关 / TUI 各自进程内一份）。"""
    global _singleton
    with _singleton_mu:
        if _singleton is None:
            _singleton = SteerQueues()
        return _singleton