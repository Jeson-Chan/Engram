"""思考强度归一化映射（runtime-knobs）— provider 差异单点维护。

档位 off/low/medium/high → 各家原生参数（bind 注入，不改构造）：
- openai_compat（ChatOpenAI 系）：``reasoning_effort="low"|"medium"|"high"``
- anthropic（ChatAnthropic）：``thinking={"type":"enabled","budget_tokens":N}``，
  并保证 ``max_tokens >= budget + 余量``（API 要求 max_tokens > budget）
- gemini（ChatGoogleGenerativeAI）：``thinking_budget=N``
- deepseek / ollama / fake / 未知：无概念 → 空 dict（静默忽略，不报错）

INVARIANT：
- 映射表只在此模块维护；调用方只问「kind + 档位 → kwargs」
- off / None → 空 dict（provider 默认行为）
"""

from __future__ import annotations

from typing import Any

from engram.backend.agents.config.provider_profile import get_provider_profile

EffortLevel = str  # "off" | "low" | "medium" | "high"

# Anthropic thinking 预算档位（token）；max_tokens 下限 = 预算 + 余量
_ANTHROPIC_BUDGETS: dict[str, int] = {"low": 4_096, "medium": 16_384, "high": 32_768}
_ANTHROPIC_MAX_TOKENS_MARGIN = 4_096
# Gemini thinkingBudget 档位
_GEMINI_BUDGETS: dict[str, int] = {"low": 1_024, "medium": 8_192, "high": 24_576}

_MAPPING_KINDS = ("openai_compat", "anthropic", "gemini")


def provider_kind_for_model(model: Any) -> str:
    """从模型实例推断 provider kind（与 build_chat_model 的 class 映射一致）。

    FallbackChatModel：按 provider_names 顺序取第一个有映射的 provider kind
    （链上混合时参数随请求携带，不兼容中转由服务端容忍/忽略——design D3 风险项）。
    """
    if model is None:
        return "unknown"
    cls = type(model).__name__
    if "Fallback" in cls:
        for name in getattr(model, "provider_names", None) or []:
            prof = get_provider_profile(name)
            if prof is not None and prof.kind in _MAPPING_KINDS:
                return prof.kind
        return "unknown"
    if "OpenAI" in cls:
        return "openai_compat"
    if "DeepSeek" in cls:
        return "deepseek"
    if "Anthropic" in cls:
        return "anthropic"
    if "GoogleGenerativeAI" in cls or "Gemini" in cls:
        return "gemini"
    if "Ollama" in cls:
        return "ollama"
    return "unknown"


def effort_kwargs(kind: str, level: EffortLevel | None) -> dict[str, Any]:
    """kind + 档位 → bind kwargs；off/None/不支持 → 空 dict。"""
    if not level or level == "off":
        return {}
    if kind == "openai_compat":
        if level in ("low", "medium", "high"):
            return {"reasoning_effort": level}
        return {}
    if kind == "anthropic":
        budget = _ANTHROPIC_BUDGETS.get(level)
        if not budget:
            return {}
        return {
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "max_tokens": budget + _ANTHROPIC_MAX_TOKENS_MARGIN,
        }
    if kind == "gemini":
        budget = _GEMINI_BUDGETS.get(level)
        if not budget:
            return {}
        return {"thinking_budget": budget}
    return {}