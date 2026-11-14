"""SSE 事件缓冲 + Last-Event-ID 重连补齐（issue 10）。

与 Redis Stream 消费者组共用同一套续传语义（讲点一致）：

        Redis Stream（巩固队列）          SSE 网关（对话/研究流）
        ─────────────────────────         ─────────────────────────
  偏移    group last-delivered-id          Last-Event-ID（客户端持有序号）
  断点    PEL pending 重放                 buffer 裁剪序号之后的缺口补发
  语义    at-least-once                   at-least-once（补发可能重复，
                                          SSE 规范本就允许——客户端按
                                          event id 幂等）

SSE 规范原生续传机制：每帧带 `id:`，客户端断线重连时自动带
`Last-Event-ID` 请求头。服务端按序号补发缺口。

实现（per-session 环形缓冲，容量 N）：
- append：事件 + 递增 id（每 session 独立序号空间）
- replay_after(last_id)：返回 last_id 之后缓冲里仍存的事件
  （超出容量的缺口无法补——200 响应头 X-Engram-Events-Dropped
  明示，客户端判断重开会话）
- 内存缓冲兜底（Redis 可用时可选 EXTERNAL 持久——本 issue 范围
  取内存缓冲：会话级生命周期短，重启即新会话，语义与 Stream 互补）
"""

from __future__ import annotations

import threading
from collections import deque

from fastapi import Request

HEADER_NAME = "last-event-id"


class SSEEventBuffer:
    """单会话的事件环形缓冲（线程安全；容量截断旧的）。"""

    def __init__(self, capacity: int = 500) -> None:
        self._events: deque[tuple[int, str]] = deque(maxlen=capacity)
        self._next_id = 1
        self._lock = threading.Lock()

    def append(self, frame: str) -> int:
        """追加一帧（含 id 行前的事件体），返分配的 id。"""
        with self._lock:
            event_id = self._next_id
            self._next_id += 1
            self._events.append((event_id, frame))
            return event_id

    def replay_after(self, last_id: int) -> list[tuple[int, str]]:
        """返回 last_id 之后仍在缓冲的事件（按序）。

        返回空列表 + dropped 标志：last_id 与缓冲首元素间隔 > 0 且
        缓冲已截断（last_id < 首元素 id - 1）表示有事件被容量淘汰。
        """
        with self._lock:
            events = list(self._events)
        if not events:
            return []
        first_id = events[0][0]
        if last_id is not None and last_id >= 1 and last_id < first_id - 1:
            # 缺口超出缓冲——无法补齐（调用方检查 dropped 标志）。
            # last_id<=0 视为从未收到任何事件：从头给全量。
            return []
        return [(eid, frame) for eid, frame in events if eid > last_id]

    @property
    def dropped(self) -> bool:
        """最老事件是否已被容量截断（重连缺口可能存在的信号）。"""
        with self._lock:
            if not self._events:
                return False
            # 已分配 id 总数 > 缓冲容量 → 有事件被截断
            return (self._next_id - 1) > len(self._events) and (
                self._events[0][0] > 1
            )

    def first_id(self) -> int | None:
        with self._lock:
            return self._events[0][0] if self._events else None


class SessionEventBuffers:
    """会话 → SSEEventBuffer 注册表（网关 app.state 持有）。"""

    def __init__(self, capacity: int = 500) -> None:
        self._buffers: dict[str, SSEEventBuffer] = {}
        self._capacity = capacity
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SSEEventBuffer:
        with self._lock:
            if session_id not in self._buffers:
                self._buffers[session_id] = SSEEventBuffer(self._capacity)
            return self._buffers[session_id]

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._buffers.pop(session_id, None)


def last_event_id_from(request: Request) -> int | None:
    """从请求头读 Last-Event-ID（缺/坏返 None = 全新订阅）。"""
    raw = request.headers.get(HEADER_NAME) or request.headers.get("Last-Event-ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def frame_with_id(event_id: int, frame: str) -> str:
    """帧加 id 行：`id: N` 前置（SSE 规范——客户端据此在重连时上报）。"""
    nl = chr(10)
    if not frame.endswith(nl + nl):
        frame = frame + nl + nl
    return "id: " + str(event_id) + nl + frame
