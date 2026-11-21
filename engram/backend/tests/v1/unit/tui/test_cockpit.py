"""TUI 研究驾驶舱回归 — tui-research-cockpit（任务 6.1/6.2/6.3/6.4）。

- 缺陷 H：弹层 Escape priority——焦点在输入控件时 Esc 也能关闭
  （McpPanel / SessionSwitcher / CockpitPanel 全覆盖）
- SessionSwitcher：离线网关显示离线态 + 新建会话项；选择新建 → 新 thread
- 驾驶舱面板：离线网关显式空态；在线数据渲染（monkeypatch 网关返回）
- 会话切换：headless EngramTUI Ctrl+K → 新建会话 → active_thread_id 变化
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from textual.app import App
from textual.widgets import TextArea

from engram.backend.app.tui.app import EngramTUI
from engram.backend.app.tui.mcp_panel import McpPanel
from engram.backend.app.tui.cockpit import (
    GatewayClient,
    InspectorPanel,
    MemoryPanel,
    RunTimelinePanel,
    SessionSwitcher,
)


def _offline_gateway() -> GatewayClient:
    """指向必然拒绝连接的端口（127.0.0.1:1 不监听）。"""
    return GatewayClient(base_url="http://127.0.0.1:1")


class _PanelApp(App):
    """承载弹层的最小宿主。"""

    def __init__(self, screen_factory) -> None:
        super().__init__()
        self._factory = screen_factory

    def compose(self):
        yield TextArea(id="host-input")

    def on_mount(self) -> None:
        self.push_screen(self._factory())


async def _run(app: App) -> Any:
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        return pilot


def test_mcp_panel_escape_closes_with_input_focus():
    """缺陷 H 回归（CommandPalette 已删，McpPanel 承接同型验证）：面板 + 输入焦点 → Esc 关闭。"""

    async def check() -> None:
        app = _PanelApp(lambda: McpPanel(None, None))
        async with app.run_test(size=(100, 30)) as pilot:
            app.query_one("#host-input", TextArea).focus()
            await pilot.pause()
            from engram.backend.app.tui.mcp_panel import McpPanel as _MP
            assert isinstance(app.screen, _MP)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, _MP)  # 已关闭

    asyncio.run(check())


def test_cockpit_panels_escape_priority():
    """驾驶舱弹层 Esc（含输入焦点）可关闭。"""

    async def check() -> None:
        for factory in (
            lambda: SessionSwitcher(_offline_gateway(), "default-user"),
            lambda: MemoryPanel(_offline_gateway(), "default-user"),
            lambda: RunTimelinePanel(_offline_gateway(), "sess-x"),
            lambda: InspectorPanel(_offline_gateway(), {}),
        ):
            app = _PanelApp(factory)
            async with app.run_test(size=(100, 30)) as pilot:
                app.query_one("#host-input", TextArea).focus()
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert not isinstance(
                    app.screen,
                    (SessionSwitcher, MemoryPanel, RunTimelinePanel, InspectorPanel),
                )

    asyncio.run(check())


async def _wait_for(obj, attr: str, timeout: float = 8.0) -> None:
    """等 thread worker 渲染完成（属性非空即就绪）。"""
    import time as _t

    deadline = _t.monotonic() + timeout
    while not getattr(obj, attr, None):
        if _t.monotonic() > deadline:
            return  # 超时：交由断言给出明确失败
        await asyncio.sleep(0.05)


async def _wait_list_items(switcher, count: int, timeout: float = 8.0) -> None:
    """等 switcher 列表渲染出至少 count 个子项，且子项内部 Label 已挂载
    （ListItem 的 children 在 mount 周期后才填充——两层时序）。"""
    import time as _t

    deadline = _t.monotonic() + timeout
    while True:
        items = switcher.query_one("#switcher-list").children
        ready = len(items) >= count and all(
            len(getattr(item, "children", [])) > 0 for item in items[:count]
        )
        if ready or _t.monotonic() > deadline:
            return
        await asyncio.sleep(0.05)


def test_session_switcher_offline_shows_offline_and_new():
    """离线网关：面板显式离线态；列表仍含新建会话项。"""

    async def check() -> None:
        app = _PanelApp(lambda: SessionSwitcher(_offline_gateway(), "default-user"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            assert isinstance(switcher, SessionSwitcher)
            await _wait_for(switcher, "offline_text")
            await _wait_list_items(switcher, 1)
            assert "离线" in switcher.offline_text
            items = switcher.query_one("#switcher-list").children
            assert len(items) == 1  # 仅"新建会话"项
            assert "新建" in str(items[0].children[0].render())
            # 选择最后一项 → dismiss("__new__")
            await pilot.press("down", "enter")
            await pilot.pause()

    asyncio.run(check())


def test_memory_panel_renders_gateway_data(monkeypatch):
    """在线数据：统计 + 记忆列表渲染（monkeypatch 网关返回）。"""

    async def check() -> None:
        gw = _offline_gateway()
        monkeypatch.setattr(
            gw, "memory_stats",
            lambda user: {"total": 6, "hot": 2, "cold": 4, "forgotten": 1, "consolidation": 1},
        )
        monkeypatch.setattr(
            gw, "memory_traces",
            lambda user, q=None: [
                {"type": "episodic", "layer": "hot", "content": "alice 的记忆", "forgotten": False},
                {"type": "semantic", "layer": "cold", "content": "巩固知识", "forgotten": True},
            ],
        )
        app = _PanelApp(lambda: MemoryPanel(gw, "default-user"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await _wait_for(app.screen, "rendered_text")
            content = app.screen.rendered_text
            assert "全部 6" in content and "热 2" in content and "冷 4" in content
            assert "alice 的记忆" in content
            assert "[已遗忘]" in content

    asyncio.run(check())


def test_run_timeline_renders_gateway_data(monkeypatch):
    async def check() -> None:
        gw = _offline_gateway()
        monkeypatch.setattr(
            gw, "runs",
            lambda sid: [
                {"run_id": "run-abc123", "status": "success"},
                {"run_id": "run-def456", "status": "error"},
            ],
        )
        monkeypatch.setattr(
            gw, "run_events",
            lambda rid: {
                "run_id": rid, "status": "success",
                "events": [
                    {"event_id": "e1", "event_type": "run.started", "payload": {}, "created_at": "2026-11-16T10:00:01"},
                    {"event_id": "e2", "event_type": "tool.started", "payload": {"tool": "bash"}, "created_at": "2026-11-16T10:00:05"},
                ],
            },
        )
        app = _PanelApp(lambda: RunTimelinePanel(gw, "sess-1"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.pause()  # worker 渲染节拍
            content = app.screen.rendered_text
            assert "run-abc123" in content
            assert "success" in content and "error" in content
            assert "tool.started" in content

    asyncio.run(check())


def _stub_runtime() -> Any:
    def _no_model(role):
        raise RuntimeError("no model")

    return SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(expert_mode=False)),
        thread_id="thread-orig-0001",
        capability_registry=SimpleNamespace(get_model=_no_model),
        researcher_model_name="stub-model",
        run_manager=SimpleNamespace(),
        leader_agent=None,
        thread_dir=None,
    )


def test_tui_session_switch_new_thread():
    """headless EngramTUI：Ctrl+K → 新建会话 → active_thread_id 变化（任务 6.1）。"""

    async def check() -> None:
        app = EngramTUI(runtime=_stub_runtime())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            original_thread = app.active_thread_id
            # 离线网关：SessionSwitcher 只剩"新建会话"项 → Enter 选新建
            app._gateway = _offline_gateway()
            await pilot.press("ctrl+k")
            await pilot.pause()
            assert isinstance(app.screen, SessionSwitcher)
            await _wait_list_items(app.screen, 1)  # worker 渲染节拍
            await pilot.press("down", "enter")  # 高亮唯一项（新建）并确认
            await pilot.pause()
            assert app.active_thread_id != original_thread  # 新 thread
            assert app.active_thread_id.startswith("thread-")

    asyncio.run(check())


def test_tui_cockpit_bindings_open_panels():
    """Ctrl+O / Ctrl+G / Ctrl+U 打开对应面板（新键位避开 CR/LF 别名——review medium）。"""

    async def check() -> None:
        app = EngramTUI(runtime=_stub_runtime())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._gateway = _offline_gateway()
            await pilot.press("ctrl+o")
            await pilot.pause()
            assert isinstance(app.screen, RunTimelinePanel)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("ctrl+g")
            await pilot.pause()
            assert isinstance(app.screen, MemoryPanel)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("ctrl+u")
            await pilot.pause()
            assert isinstance(app.screen, InspectorPanel)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(check())


def test_tui_session_switch_dismiss_record_switches_thread():
    """选已有会话：dismiss 记录 dict → thread 切换 + 进入对话态（review medium：旧实现
    二次 HTTP 拉列表且 welcome-mode 下写隐藏 log）。"""

    async def check() -> None:
        app = EngramTUI(runtime=_stub_runtime())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._on_session_picked({
                "session_id": "sess-picked",
                "thread_id": "thread-picked-77",
                "user_id": "default-user",
                "metadata": {"title": "已有会话"},
            })
            await pilot.pause()
            assert app.active_thread_id == "thread-picked-77"
            assert app._gateway_session_id == "sess-picked"
            assert app.has_class("conversation-mode")  # 脱离隐藏的欢迎态
            assert not app.has_class("welcome-mode")

    asyncio.run(check())


def test_tui_draft_not_lost_when_opening_panel():
    """打开面板不丢失输入草稿（spec：快捷键打开面板不丢失当前输入草稿）。"""

    async def check() -> None:
        app = EngramTUI(runtime=_stub_runtime())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._gateway = _offline_gateway()
            input_widget = app.query_one("#welcome-input")
            input_widget.text = "未发送的草稿"
            await pilot.pause()
            await pilot.press("ctrl+u")
            await pilot.pause()
            assert isinstance(app.screen, InspectorPanel)
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#welcome-input").text == "未发送的草稿"

    asyncio.run(check())
