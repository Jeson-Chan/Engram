"""stream config 的运行参数合并（web-skill-override / runtime-knobs 共享）。

四处消费（CLI / TUI / 网关 chat / 网关 research）的同一语义收口在此：
skill_override 恒写（空列表 = 仅自动激活）；reasoning_effort / context_window
缺省不写键 = provider 默认 / 自动推导；max_loop_steps 覆写 recursion_limit 的
loop 基数。源头值可能是 cli_state（CLI/TUI）或 ChatRequest（网关）——
统一转成 dict 后经 ``apply_stream_knobs`` 合并。
"""

from __future__ import annotations

from typing import Any


def knobs_from_cli_state(cli_state: dict[str, Any] | None) -> dict[str, Any]:
    """CLI/TUI 的 cli_state → 旋钮源（缺省即空）。"""
    if not cli_state:
        return {}
    return {
        "skill_override": list(cli_state.get("skill_override") or []),
        "reasoning_effort": cli_state.get("reasoning_effort"),
        "context_window": cli_state.get("context_window"),
        "max_loop_steps": cli_state.get("max_loop_steps"),
    }


def knobs_from_request(request: Any) -> dict[str, Any]:
    """网关 ChatRequest → 旋钮源（字段可选，缺省即空）。"""
    return {
        "skill_override": list(getattr(request, "skill_override", None) or []),
        "reasoning_effort": getattr(request, "reasoning_effort", None),
        "context_window": getattr(request, "context_window", None),
        "max_loop_steps": getattr(request, "max_loop_steps", None),
    }


def apply_stream_knobs(configurable: dict[str, Any], knobs: dict[str, Any]) -> int | None:
    """把旋钮源合并进 configurable（就地），返回覆写的 loop 基数（None=用默认）。

    - skill_override 恒写（SkillInjectionMiddleware 经 _get_runtime_value 读取）
    - reasoning_effort：off/缺省不写键（provider 默认）
    - context_window：缺省不写键（策略查表自动推导）
    - max_loop_steps：仅作为 recursion_limit 基数返回，不进 configurable
    """
    configurable["skill_override"] = list(knobs.get("skill_override") or [])
    effort = knobs.get("reasoning_effort")
    if effort and effort != "off":
        configurable["reasoning_effort"] = effort
    window = knobs.get("context_window")
    if window:
        configurable["context_window"] = window
    loop = knobs.get("max_loop_steps")
    return loop if loop else None