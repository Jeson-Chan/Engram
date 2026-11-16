"""网关启动入口 — Windows 兼容事件循环 + 启动自检快速失败。

E2E 缺陷 A（docs/e2e-baseline.md）：uvicorn 0.54 在 win32 默认创建
ProactorEventLoop，psycopg 异步驱动拒绝该循环，配置 PG DSN 的网关
启动阶段 PoolTimeout 失败。README 旧的 `uvicorn engram...main:app`
直接启动方式在 Windows + PG 下不可用。

修复（runtime-hardening / Windows 与 Postgres 启动）：
- 推荐入口 `python -m engram.backend.app.gateway`：win32 显式设置
  WindowsSelectorEventLoopPolicy，再 `uvicorn.run(app, loop="none")`
  （用当前策略创建的循环，不再让 uvicorn 自选 Proactor）。
- 兜底自检 `assert_loop_compatible_for_pg()`：即使调用方用裸 uvicorn
  启动，lifespan 在建 PG checkpointer 之前检查运行中的循环——不兼容
  立即抛 RuntimeError（秒级失败 + 可操作提示），而不是等 30 秒
  PoolTimeout。
"""

from __future__ import annotations

import asyncio
import sys


_LOOP_HINT = (
    "psycopg async requires SelectorEventLoop on Windows. "
    "Start the gateway with `python -m engram.backend.app.gateway` "
    "(it forces WindowsSelectorEventLoopPolicy), or set the policy "
    "yourself before creating the loop: "
    "asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())"
)


class IncompatibleLoopError(RuntimeError):
    """事件循环与异步 PG 驱动不兼容（Windows Proactor + psycopg）。"""


def ensure_compatible_loop_policy() -> None:
    """win32 → WindowsSelectorEventLoopPolicy；其它平台 no-op。

    必须在事件循环创建之前调用（进程启动阶段）。幂等。
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _is_proactor_loop(loop: asyncio.AbstractEventLoop) -> bool:
    return type(loop).__name__ == "ProactorEventLoop"


def assert_loop_compatible_for_pg(
    loop: asyncio.AbstractEventLoop | None = None,
    platform: str | None = None,
) -> None:
    """启动自检：win32 + ProactorEventLoop + PG 场景快速失败。

    loop None → 取当前运行/默认循环；platform None → sys.platform。
    兼容（非 win32 / Selector 循环）→ 直接返回。
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop_policy().get_event_loop() \
                if hasattr(asyncio.get_event_loop_policy(), "get_event_loop") else None
    if loop is None:
        return
    plat = platform if platform is not None else sys.platform
    if plat == "win32" and _is_proactor_loop(loop):
        raise IncompatibleLoopError(
            f"event loop {type(loop).__name__} is incompatible with async "
            f"postgres drivers on win32. {_LOOP_HINT}"
        )


def run_gateway(
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "info",
) -> None:
    """推荐启动入口（README 命令）：Selector 兼容循环 + uvicorn。"""
    ensure_compatible_loop_policy()
    import uvicorn

    from engram.backend.app.gateway.main import app

    # loop="none"：使用当前策略创建的循环（ensure 已保证 win32 → Selector），
    # 不让 uvicorn 0.54 自选 Proactor。
    uvicorn.run(app, host=host, port=port, loop="none", log_level=log_level)


if __name__ == "__main__":  # pragma: no cover
    run_gateway()
