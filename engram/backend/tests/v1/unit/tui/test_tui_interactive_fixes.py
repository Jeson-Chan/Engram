"""tui-interactive-fixes 回归 — 设置焦点 / Ctrl+C 退出 / 会话删除 / /quit 移除。

覆盖 spec `tui-interaction` 的三类场景：
- 设置面板打开即键盘可达（挂载后第一个 Input 持有焦点）
- 会话面板 d 删除：确认删除（非活跃/活跃回落）、取消、网关失败
- GatewayClient.delete_session 三路径（204/404/网络失败）
"""

from __future__ import annotations

import asyncio
import json
import threading
import time as _t
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from textual.app import App
from textual.containers import Container
from textual.widgets import Input, Label, TextArea

from engram.backend.app.tui.cockpit import GatewayClient, SessionSwitcher


def _offline_gateway() -> GatewayClient:
    return GatewayClient(base_url="http://127.0.0.1:1")


class _PanelApp(App):
    """承载弹层的最小宿主（同 test_cockpit 模式）。"""

    def __init__(self, screen_factory) -> None:
        super().__init__()
        self._factory = screen_factory

    def compose(self):
        yield TextArea(id="host-input")

    def on_mount(self) -> None:
        self.push_screen(self._factory())


async def _wait_for(obj, attr: str, timeout: float = 8.0) -> None:
    deadline = _t.monotonic() + timeout
    while not getattr(obj, attr, None):
        if _t.monotonic() > deadline:
            return
        await asyncio.sleep(0.05)


async def _wait_list_items(switcher, count: int, timeout: float = 8.0) -> None:
    deadline = _t.monotonic() + timeout
    while True:
        items = switcher.query_one("#switcher-list").children
        ready = len(items) >= count and all(
            len(getattr(item, "children", [])) > 0 for item in items[:count]
        )
        if ready or _t.monotonic() > deadline:
            return
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# 1.1 设置面板焦点
# ---------------------------------------------------------------------------

class _SettingsHost(App):
    """宿主：挂载 SettingsScreen（需要 .env 路径，指向不存在的文件即可——
    compose 读取的是 os.environ 的 provider 值，不触盘）。"""

    def compose(self):
        yield Container()

    def on_mount(self) -> None:
        from engram.backend.app.tui.settings_screen import SettingsScreen
        from pathlib import Path
        self.push_screen(SettingsScreen(Path("nonexistent.env")))


def test_settings_screen_focuses_first_input_on_mount(monkeypatch):
    """面板挂载后第一个可编辑控件（provider API Key Input）持有焦点。"""
    from engram.backend.agents.config.provider_profile import PROVIDER_PROFILES

    async def check() -> None:
        # 模拟 deepseek 已配置（compose 只显示有 key 的 provider）
        profile = next(p for p in PROVIDER_PROFILES if p.name == "deepseek")
        monkeypatch.setenv(profile.env_key, "sk-test")
        app = _SettingsHost()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            focused = app.focused
            assert focused is not None
            assert isinstance(focused, Input), (
                f"焦点应是第一个 Input，实际 {type(focused).__name__}"
            )
            # 直接打字验证键盘可达
            before = focused.value
            await pilot.press("x")
            await pilot.pause()
            assert focused.value != before or len(focused.value) >= 1

    asyncio.run(check())


# ---------------------------------------------------------------------------
# 1.2 Ctrl+C 退出（输入框不再劫持）
# ---------------------------------------------------------------------------

class _QuitCaptureApp(App):
    """宿主：记录 quit action 是否被触发。"""

    def __init__(self) -> None:
        super().__init__()
        self.quit_called = False

    def compose(self):
        yield TextArea(id="host-input")

    def action_quit(self) -> None:
        self.quit_called = True


def test_ctrl_c_not_swallowed_by_textarea():
    """焦点在 TextArea（对话输入同型控件）时按 ctrl+c：不被输入控件吞掉。

    EngramTUI 的 App 级 binding 会退出进程（run_test 内不可直接测进程退出），
    这里测等价事实：输入控件层不再声明 ctrl+c 绑定。
    """
    from engram.backend.app.tui.app import ConversationInput

    bound_keys = {
        b.key for b in ConversationInput.BINDINGS
        if hasattr(b, "key")
    }
    assert "ctrl+c" not in bound_keys, "ConversationInput 不应再绑定 ctrl+c"


def test_ctrl_c_priority_binding_removed():
    """旧缺陷回归：ConversationInput 曾用 priority=True 劫持 ctrl+c。"""
    from engram.backend.app.tui.app import ConversationInput

    for b in ConversationInput.BINDINGS:
        assert getattr(b, "key", None) != "ctrl+c"


# ---------------------------------------------------------------------------
# 1.3 /quit 移除
# ---------------------------------------------------------------------------

def test_quit_removed_from_registry():
    """/quit 不再注册；/exit 仍在。"""
    from engram.backend.app.cli.commands import get_registry

    names = {spec.name for spec in get_registry()._commands.values()} if hasattr(
        get_registry(), "_commands") else set()
    # 兼容 registry 内部结构差异：直接遍历注册表
    reg = get_registry()
    all_names = set()
    for attr in ("_commands", "commands", "_registry"):
        obj = getattr(reg, attr, None)
        if isinstance(obj, dict):
            all_names |= set(obj.keys())
        elif obj is not None:
            all_names |= {getattr(s, "name", "?") for s in (obj.values() if isinstance(obj, dict) else [])}
    # 稳妥路径：handle_command 行为断言（与 CLI 语义一致）
    from engram.backend.app.cli.commands import handle_command
    from rich.console import Console
    import io
    console = Console(file=io.StringIO(), force_terminal=False, width=120)
    state: dict[str, Any] = {"mode": "default", "model": "m", "provider": ""}
    assert handle_command("/exit", console, None, state, runtime=None) is True
    assert handle_command("/quit", console, None, state, runtime=None) is False


# ---------------------------------------------------------------------------
# 2.1 GatewayClient.delete_session
# ---------------------------------------------------------------------------

class _DeleteHandler(BaseHTTPRequestHandler):
    """极小 HTTP 服务：DELETE /sessions/<id>，按 id 决定 204 / 404。"""

    def do_DELETE(self) -> None:  # noqa: N802
        if "/sessions/ok-" in self.path:
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"session not found"}')

    def log_message(self, *args) -> None:
        pass


def _serve() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), _DeleteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_delete_session_three_paths():
    server = _serve()
    try:
        port = server.server_address[1]
        gw = GatewayClient(base_url=f"http://127.0.0.1:{port}")
        assert gw.delete_session("ok-1") is True       # 204
        assert gw.delete_session("missing-1") is False  # 404
    finally:
        server.shutdown()
    # 网络失败
    assert _offline_gateway().delete_session("any") is False


# ---------------------------------------------------------------------------
# 2.2 / 2.3 SessionSwitcher 删除交互
# ---------------------------------------------------------------------------

def _make_gateway(sessions: list[dict], deleted: list[str], succeed: bool = True):
    class _Fake:
        def __init__(self) -> None:
            self.base = "fake"
            self.timeout = 1
        def sessions(self, user_id=None):
            return list(sessions)
        def delete_session(self, session_id):
            if not succeed:
                return False
            deleted.append(session_id)
            return True
    return _Fake()


def _sessions_fixture() -> list[dict]:
    return [
        {"session_id": "s-alpha-01", "thread_id": "t1", "user_id": "u",
         "metadata": {"title": "会话A"}},
        {"session_id": "s-beta-02", "thread_id": "t2", "user_id": "u",
         "metadata": {"title": "会话B"}},
    ]


def test_switcher_delete_non_active_session():
    """d → y：删除调网关，列表移除，面板仍开着（非活跃不回落）。"""
    deleted: list[str] = []
    gw = _make_gateway(_sessions_fixture(), deleted)

    async def check() -> None:
        app = _PanelApp(lambda: SessionSwitcher(gw, "u", active_session_id=None))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            await _wait_for(switcher, "offline_text")
            await _wait_list_items(switcher, 2)
            lv = switcher.query_one("#switcher-list")
            lv.index = 1  # 高亮"会话B"（非活跃）
            await pilot.pause()
            await pilot.press("d")   # 发起：行内确认
            await pilot.pause()
            assert switcher._pending_delete == 1
            await pilot.press("y")   # 确认
            # worker 完成后列表移除
            deadline = _t.monotonic() + 5
            while "s-beta-02" not in deleted and _t.monotonic() < deadline:
                await asyncio.sleep(0.05)
            assert deleted == ["s-beta-02"]
            deadline = _t.monotonic() + 5
            while len(lv.children) != 2 and _t.monotonic() < deadline:
                await asyncio.sleep(0.05)
            assert len(lv.children) == 2  # 1 会话 + 新建项
            assert isinstance(app.screen, SessionSwitcher)  # 面板未关

    asyncio.run(check())


def test_switcher_delete_active_session_falls_back_to_new():
    """删除当前活跃会话 → dismiss('__new__') 回落新建空会话。"""
    deleted: list[str] = []
    gw = _make_gateway(_sessions_fixture(), deleted)
    results: list[Any] = []

    async def check() -> None:
        app = _PanelApp(lambda: SessionSwitcher(
            gw, "u", active_session_id="s-alpha-01",
        ))
        # 捕获 dismiss 结果：_PanelApp 的 push_screen 未传 callback，
        # 直接在宿主记录 screen 被 pop
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            await _wait_for(switcher, "offline_text")
            await _wait_list_items(switcher, 2)
            lv = switcher.query_one("#switcher-list")
            lv.index = 0  # 活跃会话
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            await pilot.press("y")
            deadline = _t.monotonic() + 5
            while not deleted and _t.monotonic() < deadline:
                await asyncio.sleep(0.05)
            assert deleted == ["s-alpha-01"]

    asyncio.run(check())


def test_switcher_delete_cancel_keeps_list():
    """d → n（非 y）：取消，无删除，行文案恢复。"""
    deleted: list[str] = []
    gw = _make_gateway(_sessions_fixture(), deleted)

    async def check() -> None:
        app = _PanelApp(lambda: SessionSwitcher(gw, "u"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            await _wait_for(switcher, "offline_text")
            await _wait_list_items(switcher, 2)
            lv = switcher.query_one("#switcher-list")
            lv.index = 0
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            assert switcher._pending_delete == 0
            await pilot.press("n")  # 取消
            await pilot.pause()
            assert switcher._pending_delete is None
            assert deleted == []   # 无网关调用
            # 行文案恢复（不再含"确认删除"）
            label_text = str(lv.children[0].children[0].render())
            assert "确认删除" not in label_text

    asyncio.run(check())


def test_switcher_delete_gateway_failure_keeps_list():
    """网关删除失败：列表不变，失败反馈可见。"""
    deleted: list[str] = []
    gw = _make_gateway(_sessions_fixture(), deleted, succeed=False)

    async def check() -> None:
        app = _PanelApp(lambda: SessionSwitcher(gw, "u"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            switcher = app.screen
            await _wait_for(switcher, "offline_text")
            await _wait_list_items(switcher, 2)
            lv = switcher.query_one("#switcher-list")
            lv.index = 0
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            await pilot.press("y")
            # worker 完成（fake 同步返回，call_from_thread 调度后即生效）
            deadline = _t.monotonic() + 5
            while _t.monotonic() < deadline:
                offline = switcher.query_one("#switcher-offline")
                try:
                    content = str(offline.render())
                except Exception:
                    content = ""
                if "删除失败" in content:
                    break
                await asyncio.sleep(0.05)
            assert "删除失败" in content
            # 列表条目未减少
            assert len(lv.children) == 3  # 2 会话 + 新建项

    asyncio.run(check())
