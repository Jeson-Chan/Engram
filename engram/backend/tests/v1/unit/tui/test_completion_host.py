"""command-completion — TUI 补全宿主 pilot 测试（真实 CompletionHost + 轻量宿主）。"""
from __future__ import annotations

import asyncio

from textual.app import App

from engram.backend.app.tui.app import ConversationInput
from engram.backend.app.tui.completion_host import CompletionHost
from engram.backend.app.tui.suggestion_popup import SuggestionPopup


class _Host(CompletionHost, App):
    """最小宿主：真实 mixin + 真实输入框/浮层。"""

    def compose(self):
        yield SuggestionPopup(id="conv-completion")
        yield ConversationInput(id="conv-input")

    def _skill_names(self) -> list[str]:
        return ["find-skills", "report-gen"]

    def _provider_names(self) -> list[str]:
        return ["qwen", "deepseek"]


def test_slash_popup_prefix_filter_tab_and_escape() -> None:
    async def check() -> None:
        app = _Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            inp = app.query_one("#conv-input", ConversationInput)
            popup = app.query_one("#conv-completion", SuggestionPopup)
            inp.focus()

            # 输入 / → 命令列表出现，首项 /help
            await pilot.press("/")
            await pilot.pause()
            assert popup.visible
            assert popup.selected == "/help"

            # 前缀过滤：/s → /skill（唯一 /s 开头）
            await pilot.press("s")
            await pilot.pause()
            assert popup.selected == "/skill"

            # Tab 补全 → "/skill "（命令后置空格），随后进入参数位候选
            await pilot.press("tab")
            await pilot.pause()
            assert inp.text == "/skill "
            assert popup.visible
            assert popup.selected == "list"  # 子命令优先

            # ↓ 移动后 Tab → 补全为 off
            await pilot.press("down")
            await pilot.pause()
            assert popup.selected == "off"
            await pilot.press("tab")
            await pilot.pause()
            assert inp.text == "/skill off "

            # Esc 关闭浮层
            await pilot.press("escape")
            await pilot.pause()
            assert not popup.visible

    asyncio.run(check())


def test_skill_name_completion_from_provider() -> None:
    async def check() -> None:
        app = _Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            inp = app.query_one("#conv-input", ConversationInput)
            popup = app.query_one("#conv-completion", SuggestionPopup)
            inp.focus()
            for ch in "/skill fin":
                await pilot.press(ch)
            await pilot.pause()
            assert popup.visible
            assert popup.selected == "find-skills"
            await pilot.press("tab")
            await pilot.pause()
            assert inp.text.startswith("/skill find-skills")

    asyncio.run(check())


def test_non_slash_input_no_popup() -> None:
    async def check() -> None:
        app = _Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            inp = app.query_one("#conv-input", ConversationInput)
            popup = app.query_one("#conv-completion", SuggestionPopup)
            inp.focus()
            for ch in "hello":
                await pilot.press(ch)
            await pilot.pause()
            assert not popup.visible

    asyncio.run(check())