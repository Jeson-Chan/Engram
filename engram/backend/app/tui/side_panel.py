"""SidePanel — 宽屏时右侧会话信息面板（textual Static + rich）。

展示：Context 用量 / 上下文窗口 / Compact 进度条 / MCP / 版本。
终端足够宽（>= 阈值）时由 App 挂 ``wide`` class 显示，窄屏隐藏。

像素风词法（tui-pixel-flavor，2026-11-20）：
- 分组标题：``▓▓▓ `` 青色点阵前缀（agent 管理的记忆结构取青侧）
- 分组之间：``░`` 重复横格线替代空行留白（格律留白）
- 明细行前缀按语义分层：``▓`` 数据（window/free/sandbox） / ``▒`` 配置
  （model/mode）/ ``●``→状态位（MCP 健康度）——同一方块家族粗细即层级
- 进度条：``▓`` 满格填充 + ``░`` 空段；>=80% 填充色转 WARN 橙
  （阈值判定沿用 pct_color 单一判定点，_bar 只接受颜色参数）
- 词法全部走 Text 手工字符拼接（D12 红线：不碰 Textual border 渲染）
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from engram.backend.app.tui import theme


def _format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}K"
    return str(tokens)


def _bar(fraction: float, width: int = 22, fill_color: str | None = None) -> Text:
    """块状进度条：▓ 满格填充 + ░ 空段。

    fill_color 缺省紫（BAR_FILL）；>=80% 由调用方传 WARN 橙
    （阈值判定单一在调用方 pct_color，bar 不重复判定）。
    """
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    t = Text()
    t.append("▓" * filled, style=fill_color or theme.BAR_FILL)
    t.append("░" * (width - filled), style=theme.BAR_EMPTY)
    return t


def _gridline(width: int = 38) -> Text:
    """分组间 ░ 横格线（格律留白，替代空行）。"""
    return Text("░" * width, style=theme.BAR_EMPTY)


class SidePanel(Static):
    """右侧会话信息面板。

    左侧竖线不用 CSS ``border-left``——见 D12：真实终端（Windows Terminal/
    PowerShell）下 border-left 在部分行会渲染出异常的白色线段（headless SVG
    导出复现不了，怀疑是该终端对 box-drawing 字符的边框特殊路径处理有关），
    改成手工在每行内容前拼一个受 theme.BORDER 控制的竖线字符，完全绕开
    Textual border 渲染路径，同时 ``height: 1fr`` 撑满整列，未占满的空白行
    背景仍是 SURFACE_ALT（不再有竖线，纯背景色分隔即可，不影响辨识度）。
    """

    DEFAULT_CSS = f"""
    SidePanel {{
        width: 44;
        height: 1fr;
        background: {theme.SURFACE_ALT};
        color: {theme.TEXT_SECONDARY};
        padding: 1 2 1 1;
    }}
    """

    def update_state(self, cli_state: dict[str, Any]) -> None:
        tokens = cli_state.get("current_tokens", 0)
        fraction = cli_state.get("current_fraction", 0.0)
        window = cli_state.get("current_window", 0)
        mcp_count = cli_state.get("mcp_count", 0)
        model = cli_state.get("model", "?")
        mode = cli_state.get("mode", "default")
        sandbox_id = cli_state.get("sandbox_id", "")
        mcp_servers = cli_state.get("mcp_servers", [])
        pct = fraction * 100.0
        pct_color = theme.ACCENT_WARN if pct >= 80 else theme.MARK_WINDOW

        def header(text: str) -> Text:
            t = Text()
            t.append("▓▓▓ ", style=theme.ACCENT_ASSISTANT)
            t.append(text, style=f"bold {theme.ACCENT_BRAND}")
            return t

        def mark_row(mark_color: str, label: str, value: str,
                     mark: str = "▓") -> Text:
            """明细行：前缀字符按语义分层——▓ 数据 / ▒ 配置 / 状态字符。"""
            t = Text()
            t.append(f"{mark} ", style=mark_color)
            t.append(f"{label}: ", style=theme.TEXT_SECONDARY)
            t.append(value, style=theme.TEXT_PRIMARY)
            return t

        lines: list[Any] = []

        # Context——顶部大字号高亮当前用量
        lines.append(header("Context"))
        ctx_line = Text()
        ctx_line.append(f"{_format_tokens(tokens)} ", style=f"bold {theme.MARK_WINDOW}")
        ctx_line.append(f"({pct:.1f}%)", style=pct_color)
        lines.append(ctx_line)
        lines.append(_gridline())

        # Context Detail——每行前缀不同语义色方块，呼应参考设计但收敛色阶
        lines.append(header("Context Detail"))
        lines.append(mark_row(theme.MARK_WINDOW, "Context window", f"{_format_tokens(window)} ({pct:.1f}%)", mark="▓"))
        lines.append(mark_row(theme.MARK_MODEL, "Model", model, mark="▒"))
        lines.append(mark_row(theme.MARK_MODE, "Mode", mode, mark="▒"))
        lines.append(mark_row(theme.MARK_MCP, "MCP tools", str(mcp_count), mark="▒"))
        free = max(0.0, 1.0 - fraction) * 100.0
        lines.append(mark_row(theme.MARK_FREE, "Free space", f"{free:.1f}%", mark="▓"))
        lines.append(_gridline())

        # Compact 进度条
        lines.append(header("Compact"))
        bar = _bar(fraction, fill_color=pct_color)
        bar.append(f"  {pct:.1f}%", style=pct_color)
        lines.append(bar)
        usable = window - tokens if window else 0
        lines.append(Text(
            f"{_format_tokens(tokens)} usage · {_format_tokens(max(0, usable))} usable",
            style=theme.TEXT_DIM,
        ))
        lines.append(_gridline())

        # Sandbox——沙箱状态
        lines.append(header("Sandbox"))
        if sandbox_id:
            lines.append(mark_row(theme.MARK_WINDOW, "Sandbox ID", sandbox_id, mark="▓"))
            lines.append(mark_row(theme.MARK_FREE, "Status", "active", mark="░"))
        else:
            lines.append(mark_row(theme.TEXT_DIM, "Sandbox ID", "—", mark="░"))
            lines.append(mark_row(theme.TEXT_DIM, "Status", "idle", mark="░"))
        lines.append(_gridline())

        # MCP——已加载 server 列表
        lines.append(header("MCP"))
        if mcp_servers:
            total_tools = sum(s.get("tool_count", 0) for s in mcp_servers)
            for s in mcp_servers:
                mark = theme.MARK_FREE if s.get("health_state") == "healthy" else theme.ACCENT_WARN
                status_dot = "▓" if s.get("health_state") == "healthy" else "░"
                row = Text()
                row.append("■ ", style=mark)
                row.append(f"{s['name']}", style=theme.TEXT_PRIMARY)
                row.append(f"  {s['transport']}  {status_dot}", style=theme.TEXT_DIM)
                lines.append(row)
            lines.append(mark_row(theme.MARK_MCP, "tools", f"{total_tools} loaded", mark="▒"))
        else:
            lines.append(mark_row(theme.TEXT_DIM, "servers", "none", mark="░"))
        lines.append(_gridline())

        # 底部版本
        lines.append(Text("Engram v1.0.0", style=theme.TEXT_DIM))

        # 手工竖线前缀（非空行才加，空行只留背景，避免竖线断续更显眼）
        prefixed: list[Any] = []
        for line in lines:
            if isinstance(line, Text) and not line.plain:
                prefixed.append(line)
                continue
            bar_line = Text("│ ", style=theme.BORDER)
            bar_line.append_text(line)
            prefixed.append(bar_line)

        self.update(Group(*prefixed))
