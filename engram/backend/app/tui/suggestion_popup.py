"""补全浮层（command-completion）— TUI 斜杠命令候选列表。

挂载在输入区相邻位置（欢迎页 InputRow / 对话页 InputBox），默认隐藏；
App 在 TextArea.Changed 时计算候选并 show()，↑↓/Tab/Esc 由输入框拦截后
经 App 方法驱动本组件（move / selected / hide）。

实现说明：不用 Static——Textual 8 的 Static.visual 在空内容/重建场景下
``render()`` 可能返回 None 触发 ``get_height`` 崩溃（widget.py:1940）；
这里用裸 Widget 自绘 Rich Text，render() 恒返回非空类型。
"""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widget import Widget

from engram.backend.app.tui import theme


class SuggestionPopup(Widget):
    """候选列表（隐藏态零占位；无候选自动隐藏）。"""

    MAX_ITEMS = 8

    DEFAULT_CSS = f"""
    SuggestionPopup {{
        height: auto;
        max-height: 10;
        display: none;
        background: {theme.SURFACE};
        color: {theme.TEXT_PRIMARY};
        padding: 0 1;
    }}
    SuggestionPopup.visible {{
        display: block;
    }}
    # 欢迎页：与 #welcome-input 同宽居中，左缘对齐输入框（ui-polish）
    #welcome-completion {{
        width: 64;
        max-width: 90%;
    }}
    """

    can_focus = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._items: list[tuple[str, str]] = []
        self._index = 0

    # ---- 渲染 ----

    def render(self) -> Text:
        if not self._items:
            return Text("")
        lines: list[Text] = []
        for i, (text, meta) in enumerate(self._items):
            marker = "▸ " if i == self._index else "  "
            line = Text(
                marker + text,
                style=theme.ACCENT_THOUGHT if i == self._index else theme.TEXT_PRIMARY,
            )
            if meta:
                line.append(f"  {meta}", style=theme.TEXT_DIM)
            lines.append(line)
        return Text("\n").join(lines)

    # ---- 状态 ----

    @property
    def visible(self) -> bool:
        return bool(self._items)

    @property
    def selected(self) -> str | None:
        return self._items[self._index][0] if self._items else None

    # ---- 操作 ----

    def show(self, items: list[tuple[str, str]], index: int = 0) -> None:
        self._items = list(items)[: self.MAX_ITEMS]
        if not self._items:
            self.hide()
            return
        self._index = max(0, min(index, len(self._items) - 1))
        self.add_class("visible")
        self.refresh(layout=True)

    def hide(self) -> None:
        self._items = []
        self._index = 0
        self.remove_class("visible")
        self.refresh(layout=True)

    def move(self, delta: int) -> None:
        if not self._items:
            return
        self._index = max(0, min(len(self._items) - 1, self._index + delta))
        self.refresh()