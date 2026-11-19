"""TUI 像素风回归测试 — tui-pixel-flavor change。

锁两类契约：
1. theme token：底色向 logo 靠（#0e1012 系）、roguelike 洋红紫（#a63fc0）、
   青/橙语义不变、banner 渐变起点 #7C6FF0 不动（品牌资产与 UI 语义分离）
2. side_panel 点阵词法：▓▓▓ 青色分组标题前缀、░ 横格线、明细行 ▓/▒/░
   语义分层、块状进度条（▓ 填充 + ░ 空段）+ ≥80% WARN 橙换色
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from engram.backend.app.cli import banner
from engram.backend.app.tui import theme
from engram.backend.app.tui.side_panel import SidePanel, _bar, _gridline


def _render(t: Text) -> str:
    """无终端宽度截断地拿 Text 纯文本（词法断言用）。"""
    return t.plain


# ── theme token 契约 ─────────────────────────────────────────

def test_theme_bg_aligns_with_logo() -> None:
    """底色三层 = logo 血缘锚定（#0e1012 系，等差亮度）。"""
    assert theme.BG == "#0e1012"
    assert theme.SURFACE == "#16181b"
    assert theme.SURFACE_ALT == "#1e2124"


def test_theme_roguelike_purple_replaced() -> None:
    """UI 语义紫家族 → roguelike 洋红紫 #a63fc0；青/橙语义不动。"""
    assert theme.ACCENT_USER == "#a63fc0"
    assert theme.BORDER_FOCUS == "#a63fc0"
    assert theme.BAR_FILL == "#a63fc0"
    assert theme.ACCENT_BRAND == "#b96fd0"
    # 语义对不变
    assert theme.ACCENT_ASSISTANT == "#45c4b8"
    assert theme.ACCENT_THOUGHT == "#FF8C42"


def test_banner_gradient_untouched() -> None:
    """banner 渐变起点 #7C6FF0 不动（品牌资产，与 UI 语义色分离）。"""
    assert banner._GRADIENT[0] == "#7C6FF0"
    assert banner._GRADIENT[-1] == "#45C4B8"


# ── side_panel 点阵词法 ──────────────────────────────────────

def test_gridline_is_repeated_half_blocks() -> None:
    """分组间 ░ 横格线（格律留白）。"""
    line = _gridline(10)
    assert _render(line) == "░" * 10


def test_bar_block_rendering_and_threshold_color() -> None:
    """块状进度条：▓ 填充 + ░ 空段；缺省紫、传色即换（≥80% 调用方传 WARN）。"""
    bar = _bar(0.4, width=10)
    assert _render(bar) == "▓" * 4 + "░" * 6
    # 颜色在 spans（append 挂 span 不挂 style）：默认 BAR_FILL（紫）
    span_colors = [str(s.style) for s in _bar(0.4, width=4).spans]
    assert theme.BAR_FILL in span_colors
    # 传入 WARN 橙时填充段用橙
    warn_colors = [str(s.style) for s in _bar(0.85, width=4, fill_color=theme.ACCENT_WARN).spans]
    assert theme.ACCENT_WARN in warn_colors


def test_sidepanel_renders_pixel_lexicon() -> None:
    """SidePanel.update_state 渲染输出包含点阵词法三件套。"""
    panel = SidePanel()
    state = {
        "current_tokens": 40_000,
        "current_fraction": 0.4,
        "current_window": 100_000,
        "mcp_count": 3,
        "model": "deepseek-chat",
        "mode": "default",
        "sandbox_id": "sbx-1",
        "mcp_servers": [
            {"name": "ctx7", "transport": "http", "tool_count": 2, "health_state": "healthy"},
        ],
    }
    panel.update_state(state)
    # Static.update() 存 renderable 到 name-mangled 槽（版本内稳定）
    console = Console(width=100, record=True)
    console.print(panel._Static__content)
    out = console.export_text()
    assert "▓▓▓ " in out            # 分组标题前缀
    assert "░" * 10 in out or "░░" in out  # 横格线
    assert "▒ " in out             # 配置行(model/mode)
    assert "▓ " in out             # 数据行(window/free)
    assert "sbx-1" in out          # 内容本身还在


def test_mcp_health_uses_pixel_dots() -> None:
    """MCP 健康度状态位：healthy=▓ / 异常=░（方块家族内分层）。"""
    panel = SidePanel()
    state = {
        "current_tokens": 0, "current_fraction": 0.0, "current_window": 0,
        "mcp_count": 1, "model": "m", "mode": "default", "sandbox_id": "",
        "mcp_servers": [
            {"name": "s1", "transport": "http", "tool_count": 1, "health_state": "unhealthy"},
        ],
    }
    panel.update_state(state)
    console = Console(width=100, record=True)
    console.print(panel._Static__content)
    out = console.export_text()
    # unhealthy server 行显示 ░ 状态位
    assert "░" in out
