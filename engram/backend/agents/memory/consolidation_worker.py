"""巩固 worker 独立进程入口 — Redis Stream 消费者（issue 08）。

独立于 Web 进程运行：Web 重启不打断巩固（Stream 事件持久在 Redis，
事件不丢；worker 重启后从消费者组偏移量继续 + 认领孤儿 pending 重放）。

用法（仓库根，需 ENGRAM_REDIS_URL + 记忆配置）：
    python -m engram.backend.agents.memory.consolidation_worker

无 Redis 配置时退出码 1 提示（本入口只在 Stream 模式有意义）。
"""

from __future__ import annotations

import logging
import os
import socket
import sys

logging.basicConfig(
    level=os.environ.get("ENGRAM_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("engram.consolidation_worker")


def _consumer_name() -> str:
    """消费者名：host-pid（组内唯一即可；重启用新名避免 PEL 归属混乱，
    孤儿消息由 XAUTOCLAIM 认领兜底）。"""
    return f"{socket.gethostname()}-{os.getpid()}"


def main() -> int:
    # 独立进程不经过 bootstrap_runtime——必须自行把 env 装载进
    # MemoryConfig 单例，否则 redis_url / storage_path 全是默认空值
    from engram.backend.agents.config.loader import load_config
    from engram.backend.agents.memory.config import get_memory_config, set_memory_config

    set_memory_config(load_config().memory)
    config = get_memory_config()
    if not config.redis_url:
        print(
            "consolidation worker requires ENGRAM_REDIS_URL "
            "(stream mode); in-process queue is used otherwise",
            file=sys.stderr,
        )
        return 1

    import redis

    from engram.backend.agents.memory.bootstrap import get_memory_provider
    from engram.backend.agents.memory.stream_queue import (
        StreamConsolidationConsumer,
    )

    provider = get_memory_provider()
    if provider is None:
        print("memory disabled (config.use empty); nothing to do", file=sys.stderr)
        return 0

    # LLM：复用 provider 侧已构造的 researcher model（无独立路由需求）
    from engram.backend.agents.config.model_router import ModelRouter

    llm = ModelRouter().build_model("researcher")

    from engram.backend.agents.memory.worker import MemoryWorker

    # 复用 MemoryWorker 的单任务处理逻辑（抽取 + consolidate），
    # 但不 start() 它的线程——只拿 _process 当 stream handler。
    processor = MemoryWorker(manager=provider.manager(), llm=llm)

    client = redis.Redis.from_url(
        config.redis_url, decode_responses=True, socket_connect_timeout=5
    )
    consumer = StreamConsolidationConsumer(
        client,
        handler=processor._process,
        consumer_name=_consumer_name(),
    )
    logger.info(
        "consolidation worker started (consumer=%s group=consolidators)",
        consumer._consumer,
    )
    consumer.run_forever()
    logger.info("consolidation worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
