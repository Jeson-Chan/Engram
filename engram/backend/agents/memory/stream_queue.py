"""Redis Stream 记忆巩固队列 — 生产者/消费者组（issue 08，唯一深度硬料）。

替换进程内 queue.Queue + 守护线程：
- 生产（Web 进程）：submit() → XADD（事件落 Stream 即持久，Web 重启不丢）
- 消费（巩固 worker 进程）：XREADGROUP ">" 读新消息 → 处理 → XACK；
  消费失败不 ack → 留在 PEL（pending entries list），重启后 XAUTOCLAIM
  认领重放（at-least-once）
- 断线续传：消费者组偏移量在 Redis 侧（group last-delivered-id），
  重启从 ">" 只拿新消息 + 认领本组 pending 的旧消息——不重不漏

核心语义（面试深挖点）：
- at-least-once：处理成功 ack 才算完成；失败/崩溃留在 pending，
  重启重放（可能重复处理——巩固幂等：重复 consolidate 被
  MemoryConflictError 幂等语义吸收）
- 消费者组：多 worker 水平扩展（每 worker 独立 name，组内负载分摊）
- 偏移量：group 维护 last-delivered-id，单消费者崩溃不影响组；
  pending 归属认领（min-idle-time 阈值）避免抢占正在处理的消息

无 Redis 时（ENGRAM_REDIS_URL 未配）回退进程内 queue.Queue 行为不变
（MemoryWorker 原路径保留）。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from langchain_core.messages import BaseMessage

from engram.backend.agents.memory.worker import MemoryTask

logger = logging.getLogger(__name__)

STREAM_KEY = "engram:mem:consolidate"
GROUP_NAME = "consolidators"
CLAIM_MIN_IDLE_MS = 30_000  # pending 超过 30s 未 ack 视为孤儿（崩溃残留），可认领重放


def _messages_to_json(messages: list[BaseMessage]) -> list[dict]:
    """BaseMessage 列表 → 可 JSON 化的结构（type + content + ToolMessage 专有字段）。"""
    out = []
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        item = {"type": m.__class__.__name__, "content": content}
        if m.__class__.__name__ == "ToolMessage":
            item["tool_call_id"] = getattr(m, "tool_call_id", "")
            if getattr(m, "name", None):
                item["name"] = m.name
        out.append(item)
    return out


def _messages_from_json(items: list[dict]) -> list[BaseMessage]:
    """JSON 结构 → BaseMessage 列表（HumanMessage/AIMessage/ToolMessage 还原）。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    mapping = {
        "HumanMessage": HumanMessage,
        "AIMessage": AIMessage,
        "ToolMessage": ToolMessage,
    }
    out = []
    for item in items:
        cls = mapping.get(item.get("type", ""), HumanMessage)
        kwargs: dict = {"content": item.get("content", "")}
        if cls is ToolMessage:
            kwargs["tool_call_id"] = item.get("tool_call_id", "")
            if item.get("name"):
                kwargs["name"] = item["name"]
        out.append(cls(**kwargs))
    return out


class StreamConsolidationQueue:
    """生产者侧：submit → XADD。Web 进程持有（bootstrap 装配）。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def submit(self, task: MemoryTask) -> None:
        """丢巩固事件到 Stream（非阻塞；Stream 常驻即持久）。"""
        payload = {
            "thread_id": task.thread_id,
            "turn_count": str(task.turn_count),
            "messages": json.dumps(
                _messages_to_json(task.messages), ensure_ascii=False
            ),
        }
        self._client.xadd(STREAM_KEY, payload)


class StreamConsolidationConsumer:
    """消费者侧：巩固 worker 进程持有。

    XREADGROUP 消费组读 + 处理 + XACK；
    启动时/每轮兜底 XAUTOCLAIM 认领孤儿 pending（崩溃残留重放）。
    handler: Callable[[MemoryTask], None]——处理抛异常则不 ack，
    消息留在 PEL 等下一轮认领重放（at-least-once）。
    """

    def __init__(
        self,
        client: Any,
        handler: Callable[[MemoryTask], None],
        *,
        consumer_name: str,
        group: str = GROUP_NAME,
        batch: int = 10,
        block_ms: int = 5_000,
        claim_min_idle_ms: int = CLAIM_MIN_IDLE_MS,
    ) -> None:
        self._client = client
        self._handler = handler
        self._consumer = consumer_name
        self._group = group
        self._batch = batch
        self._block_ms = block_ms
        self._claim_min_idle_ms = claim_min_idle_ms
        self._running = False
        self._ensure_group()

    # ---- lifecycle ----

    def _ensure_group(self) -> None:
        """幂等建组（BUSYGROUP = 已存在，跳过）。

        组的 last-delivered-id 即断线续传的偏移量——组在 Redis 侧常驻，
        消费者重启后 '>' 只取组未投递的新消息。
        """
        try:
            self._client.xgroup_create(STREAM_KEY, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def run_forever(self) -> None:
        """消费主循环（阻塞；独立进程入口调）。Ctrl-C/stop() 退出。"""
        import signal

        self._running = True

        def _graceful(signum, frame):
            self.stop()

        try:
            signal.signal(signal.SIGINT, _graceful)
            signal.signal(signal.SIGTERM, _graceful)
        except (ValueError, OSError):
            pass  # 非 主线程 / Windows 无 SIGTERM：仅靠 stop()

        while self._running:
            try:
                self.consume_once()
            except Exception as exc:
                logger.error("stream consumer loop error: %s", exc, exc_info=True)
                time.sleep(1.0)

    def stop(self) -> None:
        self._running = False

    # ---- core semantics ----

    def consume_once(self) -> int:
        """单轮：认领孤儿 pending + 读新消息 + 处理 + ack。返处理数。"""
        processed = self._reclaim_orphans()
        processed += self._read_new()
        return processed

    def _read_new(self) -> int:
        """XREADGROUP '>' 读新消息（组偏移量推进）→ 处理 → ack。"""
        replies = self._client.xreadgroup(
            self._group,
            self._consumer,
            {STREAM_KEY: ">"},
            count=self._batch,
            block=self._block_ms,
        )
        if not replies:
            return 0
        processed = 0
        for _stream, entries in replies:
            for entry_id, fields in entries:
                if self._process_and_ack(entry_id, fields):
                    processed += 1
        return processed

    def _reclaim_orphans(self) -> int:
        """XAUTOCLAIM 认领孤儿 pending（其他消费者崩溃残留）重放。

        min-idle-time 阈值保护正在处理中的消息不被抢占。
        认领后消息归本消费者——处理成功 ack，失败留 PEL 下轮再来。
        """
        try:
            result = self._client.xautoclaim(
                STREAM_KEY,
                self._group,
                self._consumer,
                min_idle_time=self._claim_min_idle_ms,
                start_id="0-0",
                count=self._batch,
            )
        except Exception:
            return 0
        # 兼容不同 redis-py 返回形态（[next, entries, deleted] / (…,)）
        entries = result[1] if len(result) >= 2 else []
        processed = 0
        for entry_id, fields in entries or []:
            if self._process_and_ack(entry_id, fields):
                processed += 1
        return processed

    def _process_and_ack(self, entry_id: str, fields: dict) -> bool:
        """单条：反序列化 → handler 处理 → 成功 ack。失败不 ack（留 PEL）。"""
        try:
            task = MemoryTask(
                thread_id=fields["thread_id"],
                messages=_messages_from_json(json.loads(fields["messages"])),
                turn_count=int(fields.get("turn_count", "0")),
            )
        except Exception as exc:
            # 载荷损坏：无法处理的消息 ack 掉（毒丸防护），避免永久重放
            logger.error("stream entry %s unparsable, acking poison: %s", entry_id, exc)
            self._client.xack(STREAM_KEY, self._group, entry_id)
            return False
        try:
            self._handler(task)
        except Exception as exc:
            logger.error(
                "stream entry %s handler failed (stays pending for replay): %s",
                entry_id, exc, exc_info=True,
            )
            return False  # 不 ack → PEL → 下轮认领重放（at-least-once）
        self._client.xack(STREAM_KEY, self._group, entry_id)
        return True

    # ---- observability ----

    def pending_count(self) -> int:
        """PEL 大小（监控/测试用）。"""
        return int(self._client.xpending(STREAM_KEY, self._group)["pending"])

    def pending_entries(self) -> list:
        """PEL 明细（重放调试用）。"""
        return self._client.xpending_range(
            STREAM_KEY, self._group, min="-", max="+", count=100
        )
