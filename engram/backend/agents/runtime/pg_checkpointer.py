"""PG 持久 checkpointer — AsyncPostgresSaver + 连接池工厂。

替换进程内 InMemorySaver 单例的持久化形态（checkpointer.py 的 TODO 落实）：
- ENGRAM_CHECKPOINT_DSN 配置时，网关 lifespan 先异步建 saver（建表一次），
  预装进 checkpointer 单例槽位，bootstrap 里的 make_lead_agent 拿到的就是它
- 进程重启后同一 DSN 读回同一会话状态；多 uvicorn worker 各持独立池、
  共享同一 PG 会话表——水平扩展从架构上成立

DSN 未配置（本地 CLI / 测试）时 get_checkpointer 仍回退 InMemorySaver，
行为不变。
"""

from __future__ import annotations

import os

from langgraph.types import Checkpointer

_ENV_KEYS = ("ENGRAM_CHECKPOINT_DSN", "ENGRAM_PG_DSN")


def pg_dsn_from_env() -> str | None:
    """读 PG DSN 环境变量；两个名字等价，ENGRAM_CHECKPOINT_DSN 优先。"""
    for key in _ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


async def create_pg_checkpointer(dsn: str | None = None) -> Checkpointer:
    """建 AsyncPostgresSaver（独立连接池 + 建表）。必须在事件循环内调用。

    pool 参数照抄官方 AsyncConnection.connect 形态：
    autocommit + dict_row（BasePostgresSaver 的 Conn 协议要求）。

    E2E 缺陷 A 兜底：win32 + Proactor 循环在建池之前秒级失败（可操作
    提示），而不是等 psycopg 拒绝后 30 秒 PoolTimeout。推荐入口
    python -m engram.backend.app.gateway 已保证 Selector 策略。
    """
    # 放在建池之前——快速失败不占连接资源；真实驱动路径必经此处
    # （lifespan / 独立调用方），fake saver 的测试 monkeypatch 本函数即可绕过。
    from engram.backend.app.gateway.entry import assert_loop_compatible_for_pg

    assert_loop_compatible_for_pg()

    from psycopg_pool import AsyncConnectionPool

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    effective = (dsn or pg_dsn_from_env() or "").strip()
    if not effective:
        raise ValueError("no postgres DSN configured (set ENGRAM_CHECKPOINT_DSN)")

    # Windows note: psycopg async rejects ProactorEventLoop, and uvicorn 0.54
    # creates Proactor by default on win32 (E2E 缺陷 A). 兼容启动走
    # `python -m engram.backend.app.gateway`（entry.py 强制 Selector 策略）；
    # lifespan 里 assert_loop_compatible_for_pg() 在这里之前快速失败。
    pool = AsyncConnectionPool(
        conninfo=effective,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "row_factory": _dict_row()},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()  # 幂等建表（checkpoints / checkpoint_writes / …）
    return saver


async def close_pg_checkpointer(saver: Checkpointer) -> None:
    """关 saver 背后的连接池（lifespan shutdown 调；非 PG saver 忽略）。"""
    pool = getattr(saver, "conn", None)
    # AsyncPostgresSaver.conn 即构造时传入的 pool；只认 AsyncConnectionPool
    from psycopg_pool import AsyncConnectionPool

    if isinstance(pool, AsyncConnectionPool):
        await pool.close()


def _dict_row():
    from psycopg.rows import dict_row

    return dict_row
