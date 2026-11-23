"""reasoning_effort 映射表单测（runtime-knobs）— 逐 kind + Fallback 推断。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engram.backend.agents.config.reasoning_effort import (
    effort_kwargs,
    provider_kind_for_model,
)


class ChatOpenAI:  # 同名类足够（kind 按类名推断）
    pass


class ChatDeepSeek:
    pass


class ChatAnthropic:
    pass


class ChatGoogleGenerativeAI:
    pass


class ChatOllama:
    pass


@pytest.mark.parametrize("model,kind", [
    (ChatOpenAI(), "openai_compat"),
    (ChatDeepSeek(), "deepseek"),
    (ChatAnthropic(), "anthropic"),
    (ChatGoogleGenerativeAI(), "gemini"),
    (ChatOllama(), "ollama"),
    (SimpleNamespace(), "unknown"),
    (None, "unknown"),
])
def test_provider_kind_for_model(model, kind) -> None:
    assert provider_kind_for_model(model) == kind


def test_fallback_kind_from_provider_names() -> None:
    class FallbackChatModel:
        def __init__(self, names: list[str]) -> None:
            self.provider_names = names

    assert provider_kind_for_model(FallbackChatModel(["qwen", "deepseek"])) == "openai_compat"
    # 链上全是无映射 provider → unknown
    assert provider_kind_for_model(FallbackChatModel(["deepseek", "ollama"])) == "unknown"
    assert provider_kind_for_model(FallbackChatModel(["anthropic"])) == "anthropic"


def test_openai_compat_mapping() -> None:
    assert effort_kwargs("openai_compat", "low") == {"reasoning_effort": "low"}
    assert effort_kwargs("openai_compat", "high") == {"reasoning_effort": "high"}


def test_anthropic_mapping_budget_and_max_tokens() -> None:
    kw = effort_kwargs("anthropic", "medium")
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 16_384}
    # API 要求 max_tokens > budget_tokens
    assert kw["max_tokens"] >= 16_384


def test_gemini_mapping() -> None:
    assert effort_kwargs("gemini", "medium") == {"thinking_budget": 8_192}


@pytest.mark.parametrize("kind", ["deepseek", "ollama", "fake", "unknown"])
def test_unsupported_kinds_empty(kind) -> None:
    assert effort_kwargs(kind, "high") == {}


@pytest.mark.parametrize("level", [None, "off"])
def test_off_or_none_empty(level) -> None:
    for kind in ("openai_compat", "anthropic", "gemini"):
        assert effort_kwargs(kind, level) == {}