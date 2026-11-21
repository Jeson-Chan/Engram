"""TUI Esc 关闭弹层回归。

App 级 escape 是 priority 绑定，会先于弹层自己的 priority escape 执行；
SettingsScreen 又是普通 Screen（不是 ModalScreen）。旧行为：打开任意面板后
按 Esc 关不掉，后续按键全被弹层吞掉，表现为 TUI "卡死在面板里"。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from textual.screen import Screen

from engram.backend.agents.capabilities.registry import CapabilityRegistry
from engram.backend.app.tui.app import EngramTUI


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        thread_id="t-esc",
        config=SimpleNamespace(runtime=SimpleNamespace(
            expert_mode=False,
            logs_root=".engram/test-logs",
            timezone="UTC",
            plan_enabled=False,
        )),
        capability_registry=CapabilityRegistry(models={}),
        mcp_manager=None,
    )


class _PlainScreen(Screen):
    """普通 push_screen 叠层（SettingsScreen 同款）。"""


def test_ctrl_p_no_response() -> None:
    """Ctrl+P 命令面板已删（tui-command-surface）：按键无响应。"""
    app = EngramTUI(runtime=_runtime())

    async def run() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+p")
            await pilot.pause()
            # 无任何面板打开——默认屏仍是主屏（非 ModalScreen）
            from textual.screen import ModalScreen
            assert not isinstance(app.screen, ModalScreen)

    asyncio.run(run())


def test_escape_pops_plain_pushed_screen() -> None:
    app = EngramTUI(runtime=_runtime())

    async def run() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(_PlainScreen())
            await pilot.pause()
            assert isinstance(app.screen, _PlainScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, _PlainScreen)

    asyncio.run(run())