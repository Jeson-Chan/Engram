"""command-completion — 共享候选函数单测（TUI/CLI 同源）。"""
from __future__ import annotations

from engram.backend.app.cli.command_completer import completion_candidates
from engram.backend.app.cli.commands import get_registry


def _texts(items) -> list[str]:
    return [c.text for c in items]


def test_slash_shows_command_names_with_meta():
    items = completion_candidates("/", get_registry(), limit=50)
    names = _texts(items)
    assert "/help" in names and "/skill" in names and "/rounds" in names
    help_item = next(c for c in items if c.text == "/help")
    assert help_item.meta  # 描述非空


def test_prefix_filter_case_insensitive():
    items = completion_candidates("/ROU", get_registry())
    assert _texts(items) == ["/rounds"]


def test_non_slash_no_candidates():
    assert completion_candidates("hello", get_registry()) == []
    assert completion_candidates("", get_registry()) == []


def test_skill_arg_subcommand_priority():
    items = completion_candidates("/skill en", get_registry(), skill_names=["english-help"])
    assert _texts(items) == ["enable"]
    assert items[0].meta == "subcommand"


def test_skill_arg_skill_names_when_no_subcommand_match():
    items = completion_candidates("/skill so", get_registry(), skill_names=["source-verification", "x"])
    assert _texts(items) == ["source-verification"]
    assert items[0].meta == "skill"


def test_skill_empty_arg_subcommands_only():
    items = completion_candidates("/skill ", get_registry(), skill_names=["find-skills"])
    assert set(_texts(items)) == {"list", "off", "enable", "disable", "install"}


def test_model_arg_providers():
    items = completion_candidates("/model qw", get_registry(), providers=["qwen", "deepseek"])
    assert _texts(items) == ["qwen"]
    assert items[0].meta == "provider"


def test_effort_levels():
    items = completion_candidates("/effort m", get_registry())
    assert _texts(items) == ["medium"]


def test_unsupported_arg_no_candidates():
    assert completion_candidates("/rounds 1", get_registry()) == []


def test_limit_respected():
    items = completion_candidates("/", get_registry(), limit=3)
    assert len(items) == 3