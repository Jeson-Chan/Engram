"""TUI 研究驾驶舱面板 — tui-research-cockpit（任务 6.1/6.2/6.3）。

Web 与 TUI 共用同一套网关只读 API（gateway-client-api）：
- Ctrl+K 会话切换器（列表 + 新建）
- Ctrl+R Run 时间线（运行历史 + 持久事件日志）
- Ctrl+M Memory 面板（统计 + 过滤列表）
- Ctrl+J Inspector（模型/模式/能力 + Context 预算）

GatewayClient：同步 HTTP（urllib，零新依赖）；`ENGRAM_GATEWAY_URL`
（默认 http://127.0.0.1:8000）。网关不在线 → 各面板显式"离线"空态，
TUI 本体的对话/研究流（进程内 runtime）不受影响——Web 故障不影响
终端入口的红线在 TUI 侧同样成立。

所有弹层 Escape 带 priority=True（缺陷 H：焦点在输入控件时也能关）。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


class GatewayClient:
    """网关只读 API 的最小同步客户端（TUI 侧）。"""

    def __init__(self, base_url: str | None = None) -> None:
        self.base = (
            base_url
            or os.environ.get("ENGRAM_GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
        )
        self.timeout = 3

    def _get(self, path: str) -> Any | None:
        try:
            req = urllib.request.Request(
                self.base + path, headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def sessions(self, user_id: str | None = None) -> list[dict] | None:
        q = f"?user_id={user_id}" if user_id else ""
        return self._get(f"/sessions{q}")

    def runs(self, session_id: str) -> list[dict] | None:
        return self._get(f"/sessions/{session_id}/runs")

    def run_events(self, run_id: str) -> dict | None:
        return self._get(f"/runs/{run_id}/events?limit=300")

    def memory_stats(self, user_id: str | None = None) -> dict | None:
        q = f"?user_id={user_id}" if user_id else ""
        return self._get(f"/memory/stats{q}")

    def memory_traces(self, user_id: str | None = None, q: str | None = None) -> list[dict] | None:
        params = ["limit=50"]
        if user_id:
            params.append(f"user_id={user_id}")
        if q:
            from urllib.parse import quote

            params.append(f"q={quote(q)}")
        return self._get("/memory/traces?" + "&".join(params))

    def status(self) -> dict | None:
        return self._get("/status")


_OFFLINE = "网关离线（ENGRAM_GATEWAY_URL）——面板数据不可用，对话流不受影响"


class CockpitPanel(ModalScreen):
    """驾驶舱弹层基类：Escape priority（缺陷 H）+ 统一容器。"""

    BINDINGS = [Binding("escape", "dismiss_panel", "Close", show=False, priority=True)]

    DEFAULT_CSS = """
    CockpitPanel { align: center middle; background: $background 40%; }
    CockpitPanel > #panel-box {
        width: 80%; height: 80%; background: $surface;
        border: solid $primary; padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="panel-box"):
            with VerticalScroll():
                yield from self.panel_content()

    def panel_content(self) -> ComposeResult:  # pragma: no cover - abstract
        yield Static("")

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)


class SessionSwitcher(ModalScreen):
    """会话切换器（Ctrl+K）：网关会话列表 + 新建（↑↓ + Enter）。"""

    BINDINGS = [Binding("escape", "dismiss_panel", "Close", show=False, priority=True)]

    DEFAULT_CSS = """
    SessionSwitcher { align: center middle; background: $background 40%; }
    SessionSwitcher > #panel-box {
        width: 80%; height: 70%; background: $surface;
        border: solid $primary; padding: 1 2;
    }
    """

    def __init__(self, gateway: GatewayClient, user_id: str) -> None:
        super().__init__()
        self._gateway = gateway
        self._user_id = user_id
        self._sessions: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="panel-box"):
            yield Static("会话切换 · ↑↓ 选择 · Enter 确认 · Esc 取消", id="switcher-title")
            yield Static("加载中…", id="switcher-offline")
            yield ListView(id="switcher-list")

    def on_mount(self) -> None:
        sessions = self._gateway.sessions(self._user_id)
        if sessions is None:
            self.offline_text = _OFFLINE + "\n本地新建会话仍可用（最后一项）。"
            self.query_one("#switcher-offline", Static).update(
                Text(self.offline_text, style="dim"),
            )
            sessions = []
        self._sessions = sessions
        items = [
            ListItem(Label(
                f"{str((s.get('metadata') or {}).get('title') or s['session_id'][:8])}"
                f"  ·  {s.get('user_id', '')}  ·  {s['session_id'][:12]}",
            ))
            for s in sessions[:30]
        ]
        items.append(ListItem(Label("＋ 新建会话（新 thread，从空对话开始）")))
        self.query_one("#switcher-list", ListView).extend(items)
        try:
            self.query_one("#switcher-list", ListView).focus()
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index if event.list_view.index is not None else -1
        if index is None or index < 0:
            return
        if index >= len(self._sessions):
            self.dismiss("__new__")
        else:
            self.dismiss(self._sessions[index]["session_id"])

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)


class RunTimelinePanel(CockpitPanel):
    """Run 时间线（Ctrl+R）：会话运行历史 + 持久事件日志。"""

    def __init__(self, gateway: GatewayClient, session_id: str | None) -> None:
        super().__init__()
        self._gateway = gateway
        self._session_id = session_id

    def panel_content(self) -> ComposeResult:
        yield Static("Run Inspector · Esc 关闭", id="timeline-title")
        yield Static("加载中…", id="timeline-content")

    def on_mount(self) -> None:
        lines = [Text("运行历史", style="bold")]
        runs = self._gateway.runs(self._session_id) if self._session_id else None
        if runs is None:
            lines.append(Text(_OFFLINE, style="dim"))
        elif not runs:
            lines.append(Text("本会话还没有运行", style="dim"))
        else:
            for r in runs[:10]:
                status = r.get("status", "?")
                style = {"success": "green", "error": "red", "running": "yellow"}.get(status, "white")
                lines.append(Text(f"● {r['run_id'][:18]}  {status}", style=style))
            latest = runs[0]
            events = self._gateway.run_events(latest["run_id"])
            if events:
                lines.append(Text(f"最近 Run 事件（{latest['run_id'][:18]}）：", style="bold"))
                for e in events.get("events", [])[:40]:
                    lines.append(
                        Text(f"  · {e.get('event_type', '')}  {(e.get('created_at') or '')[11:19]}", style="dim"),
                    )
        self.rendered_text = "\n".join(str(t) for t in lines)
        self.query_one("#timeline-content", Static).update(Text("\n").join(lines))


class MemoryPanel(CockpitPanel):
    """Memory 面板（Ctrl+M）：统计 + 最近记忆（热/冷/遗忘标注）。"""

    def __init__(self, gateway: GatewayClient, user_id: str) -> None:
        super().__init__()
        self._gateway = gateway
        self._user_id = user_id

    def panel_content(self) -> ComposeResult:
        yield Static("Memory Explorer · Esc 关闭", id="memory-title")
        yield Static("加载中…", id="memory-content")

    def on_mount(self) -> None:
        lines = [Text("Memory 面板", style="bold")]
        stats = self._gateway.memory_stats(self._user_id)
        if stats is None:
            lines.append(Text(_OFFLINE, style="dim"))
        else:
            lines.append(Text(
                f"全部 {stats.get('total', 0)} · 热 {stats.get('hot', 0)} · 冷 {stats.get('cold', 0)}"
                f" · 遗忘 {stats.get('forgotten', 0)} · 巩固 {stats.get('consolidation', 0)}",
            ))
        traces = self._gateway.memory_traces(self._user_id)
        if traces:
            lines.append(Text(""))
            for t in traces[:20]:
                layer = t.get("layer") or "?"
                flag = " [已遗忘]" if t.get("forgotten") else ""
                lines.append(Text(
                    f"  [{t.get('type', '?')}/{layer}] {str(t.get('content', ''))[:60]}{flag}",
                    style="dim",
                ))
        self.rendered_text = "\n".join(str(t) for t in lines)
        self.query_one("#memory-content", Static).update(Text("\n").join(lines))


class InspectorPanel(CockpitPanel):
    """Inspector（Ctrl+J）：模型/模式/能力 + Context 预算。"""

    def __init__(self, gateway: GatewayClient, cli_state: dict[str, Any]) -> None:
        super().__init__()
        self._gateway = gateway
        self._cli_state = cli_state

    def panel_content(self) -> ComposeResult:
        yield Static("Inspector · Esc 关闭", id="inspector-title")
        yield Static("加载中…", id="inspector-content")

    def on_mount(self) -> None:
        lines = [Text("Runtime Inspector", style="bold")]
        status = self._gateway.status()
        if status is None:
            lines.append(Text(_OFFLINE, style="dim"))
            lines.append(Text(f"本地模型：{self._cli_state.get('model', '?')}"))
        else:
            lines.append(Text(f"模型：{status.get('model') or '?'}"))
            lines.append(Text(f"模式：{status.get('mode') or '?'}"))
            lines.append(Text(f"Skills：{len(status.get('skills') or [])} 个"))
            lines.append(Text(f"MCP：{len(status.get('mcp') or [])} 个 server"))
        tokens = self._cli_state.get("current_tokens") or 0
        window = self._cli_state.get("current_window") or 0
        if window:
            pct = (self._cli_state.get("current_fraction") or 0) * 100
            lines.append(Text(f"Context：{tokens} / {window} tok（{pct:.0f}%）"))
        self.query_one("#inspector-content", Static).update(Text("\n").join(lines))
