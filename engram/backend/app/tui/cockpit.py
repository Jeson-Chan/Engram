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
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual import events
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


def capability_lines(report: Any) -> list[Text]:
    """能力矩阵 → Text 行。与 CLI `engram doctor` 消费同一份 DoctorReport。"""
    marks = {
        "on": ("●", "green"),
        "off": ("○", "dim"),
        "broken": ("✕", "red"),
    }
    lines = [Text("能力矩阵（engram doctor 同源）", style="bold")]
    deployment = getattr(report, "deployment", None)
    if deployment:
        env_label = "docker 容器（记忆层由 compose 注入）" if deployment == "docker" else "宿主机直跑（venv）"
        lines.append(Text(f"运行环境：{env_label}", style="cyan"))
    for cap in report.capabilities:
        symbol, style = marks.get(cap.state, ("?", "dim"))
        row = Text(f"{symbol} {cap.label}: {cap.state}", style=style)
        if cap.state != "on":
            row.append(f" — {cap.detail}", style="dim")
        lines.append(row)
    return lines


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

    def delete_session(self, session_id: str) -> bool:
        """DELETE /sessions/{id}：204 → True；404/网络失败 → False。

        网关端点删除注册表记录并 drop SSE 缓冲；这里只做薄封装。
        """
        try:
            req = urllib.request.Request(
                self.base + f"/sessions/{session_id}",
                headers={"Accept": "application/json"},
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 204
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def patch_session(self, session_id: str, title: str) -> dict | None:
        """PATCH /sessions/{id}（surface-parity：TUI 会话重命名）。成功返记录。"""
        body = json.dumps({"title": title}, ensure_ascii=False).encode("utf-8")
        try:
            req = urllib.request.Request(
                self.base + f"/sessions/{session_id}",
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="PATCH",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def memory_delete(
        self,
        trace_id: str | None = None,
        user_id: str | None = None,
        preview: bool = False,
    ) -> dict | None:
        """DELETE /memory/traces（surface-parity：TUI 记忆删除/清空）。

        trace_id=单条；user_id=user 粒度（TUI 面板的分区即当前用户）；
        preview=true 只返将删计数。失败 → None。
        """
        from urllib.parse import quote

        params: list[str] = []
        if trace_id is not None:
            params.append(f"trace_id={quote(trace_id)}")
        if user_id is not None:
            params.append(f"user_id={quote(user_id)}")
        if preview:
            params.append("preview=true")
        q = ("?" + "&".join(params)) if params else ""
        try:
            req = urllib.request.Request(
                self.base + "/memory/traces" + q,
                headers={"Accept": "application/json"},
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None


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


class RenamePrompt(ModalScreen):
    """会话重命名输入弹层（surface-parity）。

    打开即聚焦预填当前标题；Enter 提交（空标题拒绝并提示）、Esc 取消。
    dismiss(title: str) 提交；dismiss(None) 取消。
    """

    BINDINGS = [Binding("escape", "cancel", "取消", show=False, priority=True)]

    DEFAULT_CSS = """
    RenamePrompt { align: center middle; background: $background 40%; }
    RenamePrompt > #rename-box {
        width: 60%; height: auto; background: $surface;
        border: solid $primary; padding: 1 2;
    }
    """

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="rename-box"):
            yield Static("重命名会话（Enter 提交 · Esc 取消）", id="rename-title")
            yield Input(value=self._current, id="rename-input")

    def on_mount(self) -> None:
        try:
            self.query_one("#rename-input", Input).focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        title = event.value.strip()
        if not title:
            try:
                self.query_one("#rename-title", Static).update(
                    Text("标题不能为空——请重新输入或 Esc 取消", style="red"),
                )
            except Exception:
                pass
            return
        self.dismiss(title)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SessionSwitcher(ModalScreen):
    """会话切换器（Ctrl+K）：网关会话列表 + 新建 + 删除（↑↓ Enter / d）。"""

    BINDINGS = [Binding("escape", "dismiss_panel", "Close", show=False, priority=True)]

    DEFAULT_CSS = """
    SessionSwitcher { align: center middle; background: $background 40%; }
    SessionSwitcher > #panel-box {
        width: 80%; height: 70%; background: $surface;
        border: solid $primary; padding: 1 2;
    }
    """

    def __init__(
        self, gateway: GatewayClient, user_id: str,
        active_session_id: str | None = None,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._user_id = user_id
        self._active_session_id = active_session_id  # 删活跃会话时回落新建
        self._sessions: list[dict] = []
        self._pending_delete: int | None = None  # 行内确认态：待删列表索引
        self.offline_text = ""  # worker 完成前测试可读（空态）

    def compose(self) -> ComposeResult:
        with Vertical(id="panel-box"):
            yield Static(
                "会话切换 · ↑↓ 选择 · Enter 确认 · d 删除 · r 重命名 · Esc 取消",
                id="switcher-title",
            )
            yield Static("加载中…", id="switcher-offline")
            yield ListView(id="switcher-list")

    def on_mount(self) -> None:
        # review medium：阻塞 HTTP 不在事件循环里做——thread worker 拉数
        # 据后 call_from_thread 更新 UI（列表项构建放 _render）
        self.run_worker(self._fetch_sessions, thread=True, exclusive=True)

    def _fetch_sessions(self) -> None:
        sessions = self._gateway.sessions(self._user_id)
        # call_from_thread 是 App 的方法（Screen 没有）——经 self.app 转发
        self.app.call_from_thread(self._render_data, sessions)

    def _label_for(self, s: dict) -> str:
        return (
            f"{str((s.get('metadata') or {}).get('title') or s['session_id'][:8])}"
            f"  ·  {s.get('user_id', '')}  ·  {s['session_id'][:12]}"
        )

    def _render_data(self, sessions: list[dict] | None) -> None:
        if sessions is None:
            self.offline_text = _OFFLINE + "\n本地新建会话仍可用（最后一项）。"
            self.query_one("#switcher-offline", Static).update(
                Text(self.offline_text, style="dim"),
            )
            sessions = []
        # 只保留实际渲染的截断列表（review medium：>30 会话时"新建"项
        # 索引会落在旧列表范围内，选择"新建"会误切到未展示的会话）
        self._sessions = sessions[:30]
        items = [
            ListItem(Label(self._label_for(s)))
            for s in self._sessions
        ]
        items.append(ListItem(Label("＋ 新建会话（新 thread，从空对话开始）")))
        self.query_one("#switcher-list", ListView).extend(items)
        try:
            lv = self.query_one("#switcher-list", ListView)
            if lv.index is None:
                lv.index = 0  # 聚焦不自动高亮——d/r 需要 index
            lv.focus()
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # 确认态下 Enter 不触发切换（只认 y/N；Enter 视作取消，见 on_key）
        if self._pending_delete is not None:
            event.stop()
            return
        index = event.list_view.index if event.list_view.index is not None else -1
        if index is None or index < 0:
            return
        if index >= len(self._sessions):
            self.dismiss("__new__")
        else:
            # dismiss 完整记录（session_id/thread_id/title 一次带回——
            # 调用方不再二次 HTTP 拉列表，review medium）
            self.dismiss(self._sessions[index])

    async def on_key(self, event: events.Key) -> None:
        """d 发起删除 / r 重命名；确认态 y 确认、其余任意键取消（Enter 也取消）。"""
        if event.key == "escape":
            return  # 走 BINDINGS 的 dismiss_panel
        if self._pending_delete is None:
            if event.key == "d":
                index = self._list_index()
                if index is not None and 0 <= index < len(self._sessions):
                    self._pending_delete = index
                    self._set_item_label(index, "确认删除？y 确认 / 其他键取消")
                    self._note(Text("删除将不可恢复（含会话映射；网关侧历史独立保留）", style="yellow"))
                event.stop()  # 不落入 ListView 的键处理
            elif event.key == "r":
                # surface-parity：行内重命名（弹入输入层，Enter PATCH 提交）
                index = self._list_index()
                if index is not None and 0 <= index < len(self._sessions):
                    record = self._sessions[index]
                    current = str((record.get("metadata") or {}).get("title") or "")
                    self.app.push_screen(
                        RenamePrompt(current),
                        lambda title: self._apply_rename(record, title),
                    )
                event.stop()
            return
        # 确认态
        if event.key == "y":
            index = self._pending_delete
            self._pending_delete = None
            self._confirm_delete(index)
        else:
            self._cancel_delete()
        event.stop()

    def _list_index(self) -> int | None:
        try:
            lv = self.query_one("#switcher-list", ListView)
            return lv.index
        except Exception:
            return None

    def _set_item_label(self, index: int, text: str) -> None:
        try:
            item = self.query_one("#switcher-list", ListView).children[index]
            label = item.query_one(Label)
            label.update(text)
        except Exception:
            pass

    def _note(self, text: Text) -> None:
        try:
            self.query_one("#switcher-offline", Static).update(text)
        except Exception:
            pass

    def _confirm_delete(self, index: int) -> None:
        if index >= len(self._sessions):
            self._cancel_delete()
            return
        record = self._sessions[index]
        session_id = record["session_id"]

        def _done(deleted: bool) -> None:
            if deleted:
                self._sessions.pop(index)
                self._remove_item(index)
                self._note(Text(f"已删除会话 {session_id[:12]}", style="green"))
                # 删除的是当前活跃会话 → 回落新建空会话（复用 __new__ dismiss）
                if session_id == self._active_session_id:
                    self.dismiss("__new__")
                    return
                if not self._sessions:
                    self._note(Text("全部会话已删除", style="dim"))
            else:
                # 失败：恢复行文案，提示重试；列表不变
                self._restore_item_label(index)
                self._note(Text("删除失败（网关不可达或 404）——列表未变", style="red"))

        # 阻塞 HTTP 挪 thread worker（review medium 同款模式）
        def _run() -> None:
            deleted = self._gateway.delete_session(session_id)
            self.app.call_from_thread(_done, deleted)

        self.run_worker(_run, thread=True, exclusive=True)

    def _cancel_delete(self) -> None:
        if self._pending_delete is not None:
            self._restore_item_label(self._pending_delete)
            self._pending_delete = None
            self._note(Text("已取消", style="dim"))

    def _apply_rename(self, record: dict, title: str | None) -> None:
        """surface-parity：重命名结果回调（title None = 取消）。"""
        if title is None:
            return
        session_id = record["session_id"]

        def _done(updated: dict | None) -> None:
            if not updated:
                self._note(Text("重命名失败（网关不可达或 404）", style="red"))
                return
            record.setdefault("metadata", {})["title"] = title
            for i, s in enumerate(self._sessions):
                if s.get("session_id") == session_id:
                    self._set_item_label(i, self._label_for(s))
                    break
            self._note(Text(f"已重命名为「{title}」", style="green"))

        def _run() -> None:
            updated = self._gateway.patch_session(session_id, title)
            self.app.call_from_thread(_done, updated)

        self.run_worker(_run, thread=True, exclusive=True)

    def _remove_item(self, index: int) -> None:
        try:
            lv = self.query_one("#switcher-list", ListView)
            # children 与会话列表一一对应（会话行 + 新建行）；DOM 节点用 remove()
            if 0 <= index < len(lv.children):
                lv.children[index].remove()
            # 保持高亮在合法范围
            if lv.index is not None and lv.index >= len(lv.children):
                lv.index = max(0, len(lv.children) - 1)
        except Exception:
            pass

    def _restore_item_label(self, index: int) -> None:
        if index < len(self._sessions):
            s = self._sessions[index]
            self._set_item_label(index, (
                f"{str((s.get('metadata') or {}).get('title') or s['session_id'][:8])}"
                f"  ·  {s.get('user_id', '')}  ·  {s['session_id'][:12]}"
            ))

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)


class RunTimelinePanel(CockpitPanel):
    """Run 时间线（Ctrl+R）：会话运行历史 + 持久事件日志。"""

    def __init__(self, gateway: GatewayClient, session_id: str | None) -> None:
        super().__init__()
        self._gateway = gateway
        self._session_id = session_id
        self.rendered_text = ""  # worker 完成前测试可读（空态）

    def panel_content(self) -> ComposeResult:
        yield Static("Run Inspector · Esc 关闭", id="timeline-title")
        yield Static("加载中…", id="timeline-content")

    def on_mount(self) -> None:
        # review medium：阻塞 HTTP 挪 thread worker
        self.run_worker(self._fetch_timeline, thread=True, exclusive=True)

    def _fetch_timeline(self) -> None:
        runs = self._gateway.runs(self._session_id) if self._session_id else None
        events = self._gateway.run_events(runs[0]["run_id"]) if runs else None
        self.app.call_from_thread(self._render_data, runs, events)

    def _render_data(self, runs: list[dict] | None, events: dict | None) -> None:
        lines = [Text("运行历史", style="bold")]
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
            if events:
                lines.append(Text(f"最近 Run 事件（{latest['run_id'][:18]}）：", style="bold"))
                for e in events.get("events", [])[:40]:
                    lines.append(
                        Text(f"  · {e.get('event_type', '')}  {(e.get('created_at') or '')[11:19]}", style="dim"),
                    )
        self.rendered_text = "\n".join(str(t) for t in lines)
        self.query_one("#timeline-content", Static).update(Text("\n").join(lines))


class MemoryPanel(CockpitPanel):
    """Memory 面板（Ctrl+M）：统计 + 记忆列表。

    surface-parity：↑↓ 选择 · d 删除选中（行内确认）· c 清空当前用户分区
    （先 preview 取将删计数再确认）· Esc 关闭。分区即当前用户（TUI 面板口径）。
    """

    def __init__(self, gateway: GatewayClient, user_id: str) -> None:
        super().__init__()
        self._gateway = gateway
        self._user_id = user_id
        self._traces: list[dict] = []
        self._pending: str | None = None  # "delete" | "clear"
        self.rendered_text = ""  # worker 完成前测试可读（空态）

    def panel_content(self) -> ComposeResult:
        yield Static(
            "Memory Explorer · ↑↓ 选择 · d 删除 · c 清空 · Esc 关闭",
            id="memory-title",
        )
        yield Static("加载中…", id="memory-content")
        yield Static("", id="memory-note")
        yield ListView(id="memory-list")

    def on_mount(self) -> None:
        # review medium：阻塞 HTTP 挪 thread worker
        self.run_worker(self._fetch_memory, thread=True, exclusive=True)

    def _fetch_memory(self) -> None:
        stats = self._gateway.memory_stats(self._user_id)
        traces = self._gateway.memory_traces(self._user_id)
        self.app.call_from_thread(self._render_data, stats, traces)

    def _render_data(self, stats: dict | None, traces: list[dict] | None) -> None:
        lines = [Text("Memory 面板", style="bold")]
        if stats is None:
            lines.append(Text(_OFFLINE, style="dim"))
        else:
            lines.append(Text(
                f"全部 {stats.get('total', 0)} · 热 {stats.get('hot', 0)} · 冷 {stats.get('cold', 0)}"
                f" · 遗忘 {stats.get('forgotten', 0)} · 巩固 {stats.get('consolidation', 0)}",
            ))
        self.rendered_text = "\n".join(str(t) for t in lines)
        self.query_one("#memory-content", Static).update(Text("\n").join(lines))

        self._traces = list(traces or [])[:50]
        lv = self.query_one("#memory-list", ListView)
        lv.clear()
        if not self._traces:
            lv.append(ListItem(Label("（无记忆）")))
        else:
            for t in self._traces:
                layer = t.get("layer") or "?"
                flag = " [已遗忘]" if t.get("forgotten") else ""
                lv.append(ListItem(Label(
                    f"[{t.get('type', '?')}/{layer}] {str(t.get('content', ''))[:60]}{flag}",
                )))
        try:
            if self._traces and lv.index is None:
                lv.index = 0  # 聚焦不自动高亮——d 需要 index
            lv.focus()
        except Exception:
            pass

    # ---- 删除 / 清空（surface-parity）----

    def _note(self, text: Text) -> None:
        try:
            self.query_one("#memory-note", Static).update(text)
        except Exception:
            pass

    def _current_index(self) -> int | None:
        try:
            lv = self.query_one("#memory-list", ListView)
            return lv.index
        except Exception:
            return None

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            return  # 走 BINDINGS 的 dismiss_panel
        if self._pending is not None:
            pending = self._pending
            self._pending = None
            if event.key == "y":
                if pending == "delete":
                    self._do_delete()
                else:
                    self._do_clear()
            else:
                self._note(Text("已取消", style="dim"))
            event.stop()
            return
        if event.key == "d":
            index = self._current_index()
            if index is not None and 0 <= index < len(self._traces):
                self._pending = "delete"
                self._note(Text("确认删除选中的这条记忆？y 确认 / 其他键取消", style="yellow"))
            event.stop()
        elif event.key == "c":
            self._pending = "clear"
            self._note(Text(
                f"确认清空用户 {self._user_id} 的全部记忆？y 确认 / 其他键取消",
                style="yellow",
            ))
            self.run_worker(self._preview_clear, thread=True, exclusive=True)
            event.stop()

    def _preview_clear(self) -> None:
        preview = self._gateway.memory_delete(user_id=self._user_id, preview=True)
        count = (preview or {}).get("count", "?")
        self.app.call_from_thread(
            self._note,
            Text(f"将清空 {count} 条记忆 —— y 确认 / 其他键取消", style="yellow"),
        )

    def _do_delete(self) -> None:
        index = self._current_index()
        if index is None or not (0 <= index < len(self._traces)):
            return
        trace_id = self._traces[index].get("id")

        def _run() -> None:
            result = self._gateway.memory_delete(trace_id=trace_id)
            self.app.call_from_thread(self._after_mutation, result)

        self.run_worker(_run, thread=True, exclusive=True)

    def _do_clear(self) -> None:
        def _run() -> None:
            result = self._gateway.memory_delete(user_id=self._user_id)
            self.app.call_from_thread(self._after_mutation, result)

        self.run_worker(_run, thread=True, exclusive=True)

    def _after_mutation(self, result: dict | None) -> None:
        if result is None:
            self._note(Text("操作失败（网关不可达 / 404 / 记忆未配置）", style="red"))
            return
        deleted = result.get("deleted")
        if deleted is None:
            deleted = result.get("count", "?")
        self._note(Text(f"已删除 {deleted} 条记忆", style="green"))
        self.run_worker(self._fetch_memory, thread=True, exclusive=True)


class InspectorPanel(CockpitPanel):
    """Inspector（Ctrl+U）：模型/模式/能力 + Context 预算。"""

    def __init__(self, gateway: GatewayClient, cli_state: dict[str, Any]) -> None:
        super().__init__()
        self._gateway = gateway
        self._cli_state = cli_state
        self.rendered_text = ""  # 测试可读（worker 完成前空态）

    def panel_content(self) -> ComposeResult:
        yield Static("Inspector · Esc 关闭", id="inspector-title")
        yield Static("加载中…", id="inspector-content")

    def on_mount(self) -> None:
        # review medium：阻塞 HTTP 挪 thread worker
        self.run_worker(self._fetch_status, thread=True, exclusive=True)

    def _fetch_status(self) -> None:
        status = self._gateway.status()
        # 能力矩阵与 CLI `engram doctor` 同源（simplify-configuration D5）：
        # 同一份 DoctorReport 数据，避免 TUI 与 CLI 两套判定漂移。
        report = None
        try:
            from engram.backend.app.cli.doctor import build_report

            report = build_report(Path(__file__).resolve().parents[4])
        except Exception:
            report = None
        self.app.call_from_thread(self._render_data, status, report)

    def _render_data(self, status: dict | None, report: Any = None) -> None:
        lines = [Text("Runtime Inspector", style="bold")]
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

        # runtime-knobs：三旋钮当前值与来源（manual=本会话设置 / auto=缺省）
        # surface-parity：来源标注与 web Configs 面板一致（manual: X / auto）
        rounds = self._cli_state.get("max_loop_steps")
        effort = self._cli_state.get("reasoning_effort")
        window_override = self._cli_state.get("context_window")
        # spec runtime-knobs：思考强度条目 MUST 标注当前 provider 是否支持
        supported = ""
        try:
            from engram.backend.agents.config.reasoning_effort import (
                effort_kwargs,
                provider_kind_for_model,
            )

            registry = getattr(getattr(self.app, "runtime", None), "capability_registry", None)
            if registry is not None and hasattr(registry, "get_model"):
                kind = provider_kind_for_model(registry.get_model("researcher"))
                supported = "" if effort_kwargs(kind, "low") else "（当前 provider 不支持）"
        except Exception:
            supported = ""
        lines.append(Text(
            f"轮数预算：{f'manual: {rounds}' if rounds else 'auto'}  "
            f"思考强度：{f'manual: {effort}' if effort else 'auto（provider 默认）'}{supported}  "
            f"窗口覆写：{f'manual: {window_override}' if window_override else 'auto'}"
        ))

        if report is not None:
            lines.append(Text(""))
            lines.extend(capability_lines(report))
        self.rendered_text = "\n".join(str(t) for t in lines)
        self.query_one("#inspector-content", Static).update(Text("\n").join(lines))
