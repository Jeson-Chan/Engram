"""Windows 事件循环选择测试 — runtime-hardening / Windows 与 Postgres 启动。

E2E 缺陷 A 回归：uvicorn 0.54 win32 默认 ProactorEventLoop，
psycopg 异步拒绝 → 网关带 PG DSN 启动 PoolTimeout。

修复验证点：
- ensure_compatible_loop_policy：win32 设置 WindowsSelectorEventLoopPolicy
- assert_loop_compatible_for_pg：win32 + Proactor 循环快速失败（含可操作提示）；
  Selector / 非 win32 循环通过
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from engram.backend.app.gateway.entry import (
    IncompatibleLoopError,
    assert_loop_compatible_for_pg,
    ensure_compatible_loop_policy,
)


class TestEnsureCompatibleLoopPolicy:
    def test_win32_sets_selector_policy(self):
        if sys.platform != "win32":
            pytest.skip("win32-only policy assertion")
        original = asyncio.get_event_loop_policy()
        try:
            ensure_compatible_loop_policy()
            assert isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy)
        finally:
            asyncio.set_event_loop_policy(original)

    def test_non_win32_is_noop(self):
        # 任何平台调用都不抛异常（非 win32 为 no-op）
        original = asyncio.get_event_loop_policy()
        try:
            ensure_compatible_loop_policy()
            assert asyncio.get_event_loop_policy() is original or sys.platform == "win32"
        finally:
            asyncio.set_event_loop_policy(original)


class TestAssertLoopCompatible:
    def test_win32_proactor_fails_fast_with_hint(self):
        proactor = type("ProactorEventLoop", (), {})()
        with pytest.raises(IncompatibleLoopError) as exc_info:
            assert_loop_compatible_for_pg(loop=proactor, platform="win32")
        message = str(exc_info.value)
        # 可操作：说明如何切换到兼容循环
        assert "SelectorEventLoop" in message
        assert "python -m engram.backend.app.gateway" in message

    def test_win32_selector_loop_passes(self):
        selector = type("SelectorEventLoop", (), {})()
        assert_loop_compatible_for_pg(loop=selector, platform="win32")  # 不抛

    def test_linux_proactor_passes(self):
        proactor = type("ProactorEventLoop", (), {})()
        assert_loop_compatible_for_pg(loop=proactor, platform="linux")  # 不抛

    def test_none_loop_uses_running_loop(self):
        # loop=None → 取当前运行循环。Selector 策略下（真实入口行为）通过。
        async def _check():
            assert_loop_compatible_for_pg(platform="win32")
        # Windows*Policy 仅存在于 win32；Linux 默认策略即 selector 循环，
        # 测试意图（loop=None 取运行循环 + 非 Proactor 通过）两平台一致。
        original = asyncio.get_event_loop_policy()
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            asyncio.run(_check())
        finally:
            asyncio.set_event_loop_policy(original)

    def test_error_is_runtime_error_subclass(self):
        assert issubclass(IncompatibleLoopError, RuntimeError)


@pytest.mark.skipif(sys.platform != "win32", reason="real loop check on win32")
class TestRealLoopsOnWindows:
    def test_real_selector_loop_passes(self):
        async def _check():
            assert_loop_compatible_for_pg()  # 当前运行循环
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            asyncio.run(_check())
        finally:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    def test_real_proactor_loop_fails_fast(self):
        async def _check():
            with pytest.raises(IncompatibleLoopError):
                assert_loop_compatible_for_pg()
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.run(_check())  # 秒级失败，不等 PoolTimeout
        finally:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
