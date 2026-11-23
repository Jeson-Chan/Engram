"""CompletionHost — TUI 斜杠命令补全的宿主逻辑（command-completion）。

EngramTUI 与测试宿主共用本 mixin：负责
- TextArea.Changed → 计算候选 → 刷新相邻 SuggestionPopup
- 浮层可见时消费 ↑↓/Tab/Esc（completion_key）
- Tab 接受候选：替换当前词并补尾随空格、移动光标

宿主需提供：``_skill_names() -> list[str]``、``_provider_names() -> list[str]``，
并在 compose 中挂载 SuggestionPopup（id 映射见 COMPLETION_POPUPS）。
"""
from __future__ import annotations

from typing import Any

from engram.backend.app.cli.command_completer import completion_candidates
from engram.backend.app.cli.commands import get_registry
from engram.backend.app.tui.suggestion_popup import SuggestionPopup


class CompletionHost:
    """App 侧补全 mixin（方法依赖 Textual App 的 query_one）。"""

    COMPLETION_POPUPS = {
        "welcome-input": "#welcome-completion",
        "conv-input": "#conv-completion",
    }

    # ---- 宿主数据源（子类覆盖）----

    def _skill_names(self) -> list[str]:  # pragma: no cover - 子类实现
        return []

    def _provider_names(self) -> list[str]:  # pragma: no cover - 子类实现
        return []

    # ---- 内部 ----

    def _completion_popup(self, text_area: Any) -> SuggestionPopup | None:
        selector = self.COMPLETION_POPUPS.get(getattr(text_area, "id", "") or "")
        if selector is None:
            return None
        try:
            return self.query_one(selector, SuggestionPopup)  # type: ignore[attr-defined]
        except Exception:
            return None

    def _completion_items(self, text_area: Any) -> list[tuple[str, str]]:
        try:
            row, col = text_area.cursor_location
            line = text_area.document.get_line(row)
        except Exception:
            return []
        candidates = completion_candidates(
            line[:col],
            get_registry(),
            skill_names=self._skill_names(),
            providers=self._provider_names(),
        )
        return [(c.text, c.meta) for c in candidates]

    # ---- 公共入口 ----

    def on_text_area_changed(self, event: Any) -> None:
        """输入变化 → 重算候选并刷新浮层。"""
        self._refresh_completions(event.text_area)

    def _refresh_completions(self, text_area: Any) -> None:
        popup = self._completion_popup(text_area)
        if popup is None:
            return
        items = self._completion_items(text_area)
        if items:
            popup.show(items)
        else:
            popup.hide()

    def completion_key(self, text_area: Any, key: str) -> bool:
        """浮层可见时消费 ↑↓/Tab/Esc；返回是否已处理（False = 交还 TextArea）。"""
        popup = self._completion_popup(text_area)
        if popup is None or not popup.visible:
            return False
        if key == "up":
            popup.move(-1)
            return True
        if key == "down":
            popup.move(1)
            return True
        if key == "tab":
            self._accept_completion(text_area, popup)
            return True
        if key == "escape":
            popup.hide()
            return True
        return False

    def _accept_completion(self, text_area: Any, popup: SuggestionPopup) -> None:
        item = popup.selected
        if not item:
            popup.hide()
            return
        try:
            row, col = text_area.cursor_location
            line = text_area.document.get_line(row)
        except Exception:
            popup.hide()
            return
        before = line[:col]
        start = max(before.rfind(" "), before.rfind("\t")) + 1
        insert = item if item.endswith(" ") else item + " "
        text_area.replace(insert, (row, start), (row, col))
        text_area.move_cursor((row, start + len(insert)))
        popup.hide()