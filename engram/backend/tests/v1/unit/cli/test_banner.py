"""Banner 测试 — memory 主变体 wordmark（GitHub 同款 tall 点阵 + 紫青渐变）。"""

from __future__ import annotations

from engram.backend.app.cli.banner import (
    _GRADIENT,
    _PIXEL_ENGRAM,
    _gradient_for,
    render_banner,
    render_logo,
)


def test_banner_uses_memory_variant_wordmark() -> None:
    banner = render_banner("ENGRAM")

    text_str = str(banner)

    # tall 点阵 wordmark（GitHub 展示同款 ▓ 满格字符）
    assert "▓▓▓▓▓▓▓▓▓▓" in text_str
    # Version line
    assert "v1.0.0" in text_str
    # Tagline
    assert "Long-term memory research agent" in text_str
    # 无手写 ANSI 码（rich Text 承载颜色）
    assert "\x1b[38;2;255;179;71m" not in text_str
    # 旧装饰不再出现
    assert "♦" not in text_str
    assert "★" not in text_str


def test_wordmark_is_github_tall_matrix() -> None:
    """点阵与 docs/assets/engram-banner.txt（GitHub README 头像资产）一致。"""
    from pathlib import Path

    asset = (
        Path(__file__).parents[6] / "docs" / "assets" / "engram-banner.txt"
    ).read_text(encoding="utf-8")
    asset_rows = [line for line in asset.splitlines() if line.strip()]
    assert _PIXEL_ENGRAM == asset_rows  # 同一 wordmark


def test_gradient_violet_to_teal() -> None:
    """memory 变体色对：violet #7C6FF0 → teal #45C4B8（logo/README.md 主变体）。"""
    assert _GRADIENT[0] == "#7C6FF0"
    assert _GRADIENT[-1] == "#45C4B8"
    # 行渐变首尾即 brand 色对
    gradient = _gradient_for(_PIXEL_ENGRAM)
    assert gradient[0] == "#7C6FF0"
    assert gradient[-1] == "#45C4B8"


def test_render_logo_rows_independent_colors() -> None:
    """render_logo 每行独立着色、行数与点阵一致（TUI 居中展示契约）。"""
    logo = render_logo()
    text_str = str(logo)
    assert text_str.count("\n") == len(_PIXEL_ENGRAM) - 1
    assert "▓" in text_str
