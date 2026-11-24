"""surface-parity — TUI 侧：会话重命名 / 记忆删除与清空 / Inspector 来源标注。"""
from __future__ import annotations

import asyncio
import time

from textual.app import App

from engram.backend.app.tui.cockpit import (
    GatewayClient,
    InspectorPanel,
    MemoryPanel,
    RenamePrompt,
    SessionSwitcher,
)


def _gw() -> GatewayClient:
    return GatewayClient(base_url="http://127.0.0.1:1")


class _PanelApp(App):
    def __init__(self, screen_factory) -> None:
        super().__init__()
        self._factory = screen_factory
        self.results: list = []

    def compose(self):
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(self._factory())


async def _wait_for(obj, attr: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while not getattr(obj, attr, None):
        if time.monotonic() > deadline:
            raise AssertionError(f"timeout waiting {attr}")
        await asyncio.sleep(0.02)


def _sessions() -> list[dict]:
    return [
        {"session_id": "sess-1", "thread_id": "t1", "user_id": "u",
         "metadata": {"title": "旧标题"}},
    ]


def test_session_rename_flow(monkeypatch):
    """真实在线数据路径：r → 输入 → Enter → PATCH 调用且行更新。"""
    calls: list[tuple[str, str]] = []

    async def check() -> None:
        gw = _gw()
        monkeypatch.setattr(gw, "sessions", lambda user: _sessions())
        monkeypatch.setattr(
            gw, "patch_session",
            lambda sid, title: calls.append((sid, title)) or {
                "session_id": sid, "metadata": {"title": title},
            },
        )
        app = _PanelApp(lambda: SessionSwitcher(gw, "u"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            await _wait_for(switcher, "_sessions", timeout=8)
            while not switcher._sessions:
                await asyncio.sleep(0.02)
            await pilot.press("r")
            await pilot.pause()
            prompt = app.screen
            assert isinstance(prompt, RenamePrompt)
            inp = prompt.query_one("#rename-input")
            inp.value = "新标题"
            await pilot.press("enter")
            await pilot.pause()
            # PATCH 已调用（worker 线程，稍候）
            for _ in range(200):
                if calls:
                    break
                await asyncio.sleep(0.02)
            assert calls == [("sess-1", "新标题")]
            label = switcher.query_one("#switcher-list").children[0].children[0]
            for _ in range(200):
                if "新标题" in str(label.render()):
                    break
                await asyncio.sleep(0.02)
            assert "新标题" in str(label.render())

    asyncio.run(check())


def test_memory_delete_single(monkeypatch):
    calls: list[dict] = []

    async def check() -> None:
        gw = _gw()
        monkeypatch.setattr(gw, "memory_stats", lambda user: {"total": 1, "hot": 1, "cold": 0, "forgotten": 0, "consolidation": 0})
        monkeypatch.setattr(
            gw, "memory_traces",
            lambda user, q=None: [{"id": "tr-1", "type": "episodic", "layer": "hot", "content": "x"}],
        )
        monkeypatch.setattr(
            gw, "memory_delete",
            lambda trace_id=None, user_id=None, preview=False: calls.append(
                {"trace_id": trace_id, "user_id": user_id, "preview": preview}
            ) or {"deleted": 1, "count": 1},
        )
        app = _PanelApp(lambda: MemoryPanel(gw, "u"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            panel = app.screen
            for _ in range(200):
                if panel._traces:
                    break
                await asyncio.sleep(0.02)
            assert panel._traces
            await pilot.press("d")
            await pilot.pause()
            assert panel._pending == "delete"
            await pilot.press("y")
            await pilot.pause()
            for _ in range(200):
                if calls and calls[0]["trace_id"]:
                    break
                await asyncio.sleep(0.02)
            assert calls[0]["trace_id"] == "tr-1"

    asyncio.run(check())


def test_memory_clear_partition(monkeypatch):
    calls: list[dict] = []

    async def check() -> None:
        gw = _gw()
        monkeypatch.setattr(gw, "memory_stats", lambda user: {"total": 2})
        monkeypatch.setattr(
            gw, "memory_traces",
            lambda user, q=None: [
                {"id": "tr-1", "type": "episodic", "layer": "hot", "content": "a"},
                {"id": "tr-2", "type": "semantic", "layer": "cold", "content": "b"},
            ],
        )
        monkeypatch.setattr(
            gw, "memory_delete",
            lambda trace_id=None, user_id=None, preview=False: calls.append(
                {"trace_id": trace_id, "user_id": user_id, "preview": preview}
            ) or ({"count": 2} if preview else {"deleted": 2, "count": 2}),
        )
        app = _PanelApp(lambda: MemoryPanel(gw, "u"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            panel = app.screen
            for _ in range(200):
                if panel._traces:
                    break
                await asyncio.sleep(0.02)
            await pilot.press("c")
            await pilot.pause()
            assert panel._pending == "clear"
            await pilot.press("y")
            await pilot.pause()
            for _ in range(200):
                if any(c["user_id"] == "u" and not c["preview"] for c in calls):
                    break
                await asyncio.sleep(0.02)
            assert any(c["user_id"] == "u" and c["preview"] for c in calls)
            assert any(c["user_id"] == "u" and not c["preview"] for c in calls)

    asyncio.run(check())


def test_inspector_manual_auto_markers():
    async def check() -> None:
        gw = _gw()
        cli_state = {"max_loop_steps": 10, "reasoning_effort": None, "context_window": None}
        app = _PanelApp(lambda: InspectorPanel(gw, cli_state))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            panel = app.screen
            await _wait_for(panel, "rendered_text")
            assert "manual: 10" in panel.rendered_text
            assert panel.rendered_text.count("auto") >= 2

    asyncio.run(check())