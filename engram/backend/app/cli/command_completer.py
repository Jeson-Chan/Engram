"""command_completer — ``/`` 命令补全（CLI prompt_toolkit + TUI 浮层共用）。

共享候选规则（command-completion D2，两端同构）：
- 命令名位（``/`` 开头、无空格）→ 注册表命令名前缀过滤（带描述）
- ``/skill <arg>`` → 子命令（list/off/enable/disable/install）优先，无命中补 skill 名
- ``/model <arg>`` → provider 列表
- ``/effort <arg>`` → off/low/medium/high
- ``/prompt <arg>`` → list/show/reload
- 其他命令参数位 → 无候选

CLI 用 ``SlashCommandCompleter`` 包装为 prompt_toolkit Completion；
TUI 用 ``completion_candidates`` 直接驱动补全浮层。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from engram.backend.app.cli.registry import CommandRegistry

_SKILL_SUBCOMMANDS = ("list", "off", "enable", "disable", "install")
_PROMPT_SUBCOMMANDS = ("list", "show", "reload")
_EFFORT_LEVELS = ("off", "low", "medium", "high")


@dataclass(frozen=True)
class CompletionCandidate:
    """一条补全候选：text = 待补全词，meta = 展示用说明。"""

    text: str
    meta: str = ""


def completion_candidates(
    text_before_cursor: str,
    registry: CommandRegistry,
    skill_names: list[str] | None = None,
    providers: list[str] | None = None,
    limit: int = 8,
) -> list[CompletionCandidate]:
    """光标前文本 → 候选列表（前缀过滤、子命令优先、最多 limit 条）。"""
    line = text_before_cursor.lstrip()
    if not line.startswith("/"):
        return []

    trailing_space = line.endswith(" ") or line.endswith("\t")
    tokens = line.split()

    # 命令名位：仅有单个 token 且不在参数位
    if len(tokens) == 1 and not trailing_space:
        word = tokens[0].lower()
        out = [
            CompletionCandidate(spec.name, spec.description)
            for spec in registry.list_all()
            if spec.name.lower().startswith(word)
        ]
        return out[:limit]

    if len(tokens) == 0:
        return []
    cmd = tokens[0]
    current = "" if trailing_space else tokens[-1]
    cur_lower = current.lower()

    def _filter(values: tuple[str, ...] | list[str], meta: str) -> list[CompletionCandidate]:
        return [CompletionCandidate(v, meta) for v in values if v.lower().startswith(cur_lower)][:limit]

    if cmd == "/skill":
        subs = _filter(_SKILL_SUBCOMMANDS, "subcommand")
        if subs:
            return subs
        return _filter(list(skill_names or []), "skill")
    if cmd == "/model":
        return _filter(list(providers or []), "provider")
    if cmd == "/effort":
        return _filter(_EFFORT_LEVELS, "level")
    if cmd == "/prompt":
        return _filter(_PROMPT_SUBCOMMANDS, "subcommand")
    # spec command-completion：/rounds /window 参数位显示取值提示（不强制选中）
    if cmd == "/rounds":
        return [CompletionCandidate("<n>", "轮数（≥1 整数）/ off")]
    if cmd == "/window":
        return [CompletionCandidate("<n>", "token 数（≥1000）/ off")]
    return []


class SlashCommandCompleter(Completer):
    """prompt_toolkit 适配层：共享 ``completion_candidates`` 驱动 CLI 补全。"""

    def __init__(
        self,
        registry: CommandRegistry,
        skill_provider: Callable[[], list[str]] | None = None,
        provider_provider: Callable[[], list[str]] | None = None,
    ) -> None:
        self._registry = registry
        self._skill_provider = skill_provider
        self._provider_provider = provider_provider

    def get_completions(self, document: Document, complete_event):  # type: ignore[no-untyped-def]
        def _safe(fn: Callable[[], list[str]] | None) -> list[str]:
            if fn is None:
                return []
            try:
                return fn() or []
            except Exception:
                return []

        candidates = completion_candidates(
            document.text_before_cursor,
            self._registry,
            skill_names=_safe(self._skill_provider),
            providers=_safe(self._provider_provider),
        )
        if not candidates:
            return
        word = document.get_word_before_cursor(WORD=True)
        for c in candidates:
            yield Completion(
                text=c.text,
                start_position=-len(word),
                display=c.text,
                display_meta=c.meta,
            )