"""Engram CLI banner — rich 渲染，memory 主变体（紫→青渐变）。

与 GitHub 展示的 wordmark（logo/ 的 ascii.rest memory 变体：tall 点阵、
▓ 满格字符、#7c6ff0→#45c4b8 渐变）同一设计系统——仓库 README badge、
og-image、TUI/CLI 启动 banner 读作一体。

不再用 colorama 手写 ANSI 码——rich Text + Style（避免与 rich Console 冲突）。
"""

from __future__ import annotations

from rich.text import Text

# memory 变体渐变：violet -> teal（logo/README.md 的主变体色对，7 行内插）
_GRADIENT = [
    "#7C6FF0",  # violet（brand 紫）
    "#756FEE",
    "#6E6DE9",
    "#616CDF",
    "#5275D2",
    "#4B8AC9",
    "#45C4B8",  # teal（brand 青）
]
_VERSION_COLOR = "#45C4B8"  # teal

# ENGRAM wordmark —— GitHub 展示同款 tall 点阵（docs/assets/engram-banner.txt）。
# 6 行 ▓ 满格；渐变按行插值。
_PIXEL_ENGRAM = [
    "▓▓▓▓▓▓▓▓▓▓  ▓▓      ▓▓    ▓▓▓▓▓▓    ▓▓▓▓▓▓▓▓      ▓▓▓▓▓▓    ▓▓      ▓▓",
    "▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓  ▓▓▓▓  ▓▓▓▓",
    "▓▓          ▓▓▓▓    ▓▓  ▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓  ▓▓  ▓▓",
    "▓▓▓▓▓▓▓▓    ▓▓  ▓▓  ▓▓  ▓▓  ▓▓▓▓▓▓  ▓▓▓▓▓▓▓▓    ▓▓▓▓▓▓▓▓▓▓  ▓▓  ▓▓  ▓▓",
    "▓▓          ▓▓    ▓▓▓▓  ▓▓      ▓▓  ▓▓  ▓▓      ▓▓      ▓▓  ▓▓      ▓▓",
    "▓▓          ▓▓      ▓▓  ▓▓      ▓▓  ▓▓    ▓▓    ▓▓      ▓▓  ▓▓      ▓▓",
    "▓▓▓▓▓▓▓▓▓▓  ▓▓      ▓▓    ▓▓▓▓▓▓    ▓▓      ▓▓  ▓▓      ▓▓  ▓▓      ▓▓",
]


def _gradient_for(rows: list[str]) -> list[str]:
    """逐行插值渐变（行数任意——7 色 gradient 映射到行数）。

    6 行时取首尾间均匀采样（首尾必是 violet/teal，与 web 版一致）。
    """
    n = len(rows)
    if n == len(_GRADIENT):
        return list(_GRADIENT)
    out = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0
        pos = t * (len(_GRADIENT) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(_GRADIENT) - 1)
        frac = pos - lo
        # 简单 hex 线性插值
        def mix(a: str, b: str, f: float) -> str:
            ia = int(a[1:], 16)
            ib = int(b[1:], 16)
            r = int(((ia >> 16) & 255) * (1 - f) + ((ib >> 16) & 255) * f)
            g = int(((ia >> 8) & 255) * (1 - f) + ((ib >> 8) & 255) * f)
            bl = int((ia & 255) * (1 - f) + (ib & 255) * f)
            return f"#{r:02X}{g:02X}{bl:02X}"

        out.append(mix(_GRADIENT[lo], _GRADIENT[hi], frac))
    return out


def render_logo() -> Text:
    """仅返回渐变 wordmark（不含版本/tagline），供 TUI 居中展示。

    每行独立着色，行尾不留多余空格，便于 ``width: auto`` 容器精确居中。
    """
    result = Text(justify="center")
    gradient = _gradient_for(_PIXEL_ENGRAM)
    for idx, row in enumerate(_PIXEL_ENGRAM):
        result.append(row, style=gradient[idx])
        if idx < len(_PIXEL_ENGRAM) - 1:
            result.append("\n")
    return result


def render_banner(text: str = "ENGRAM") -> Text:
    """返回 rich Text 对象，供 console.print() 渲染。

    memory 主变体 wordmark + 版本号 + tagline。不用手写 ANSI 码。
    """
    result = Text()

    upper = text.upper()
    if upper == "ENGRAM":
        gradient = _gradient_for(_PIXEL_ENGRAM)
        for idx, row in enumerate(_PIXEL_ENGRAM):
            result.append(row, style=gradient[idx])
            result.append("\n")
    else:
        result.append(upper, style=_GRADIENT[0])
        result.append("\n")

    result.append("\n")
    result.append("v1.0.0", style=_VERSION_COLOR)
    result.append("  ·  Long-term memory research agent\n", style="dim")
    return result


def print_banner() -> None:
    """CLI 启动打印（console.print 由调用方持有）。"""
    from rich.console import Console

    Console().print(render_banner())
