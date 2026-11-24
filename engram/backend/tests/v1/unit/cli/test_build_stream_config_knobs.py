"""代码审查修复回归 — TUI 旋钮经 _build_stream_config 真正生效（此前纯摆设）。"""
from __future__ import annotations

from types import SimpleNamespace

from engram.backend.app.cli.main import _build_stream_config


def _ctx(max_loop_steps: int = 4, multiplier: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        run_id="r1", thread_id="t1", journal=None, output_dir="o",
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                expert_mode=False, plan_enabled=True, timezone="UTC",
                max_loop_steps=max_loop_steps, graph_node_multiplier=multiplier,
            )
        ),
    )


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        capability_registry=SimpleNamespace(get_model=lambda role: SimpleNamespace()),
    )


def test_cli_state_knobs_merge_into_config() -> None:
    state = {
        "skill_override": ["find-skills"],
        "reasoning_effort": "low",
        "context_window": 32000,
        "max_loop_steps": 10,
    }
    cfg = _build_stream_config(_runtime(), _ctx(), state)
    assert cfg["configurable"]["skill_override"] == ["find-skills"]
    assert cfg["configurable"]["reasoning_effort"] == "low"
    assert cfg["configurable"]["context_window"] == 32000
    assert cfg["recursion_limit"] == 10 * 3


def test_cli_state_none_is_baseline() -> None:
    cfg = _build_stream_config(_runtime(), _ctx())
    assert "reasoning_effort" not in cfg["configurable"]
    assert "context_window" not in cfg["configurable"]
    assert cfg["recursion_limit"] == 4 * 3


def test_off_effort_and_empty_overrides_no_keys() -> None:
    cfg = _build_stream_config(_runtime(), _ctx(), {"reasoning_effort": "off"})
    assert "reasoning_effort" not in cfg["configurable"]
    assert cfg["configurable"]["skill_override"] == []


def test_shared_helper_single_source() -> None:
    """CLI / TUI / 网关共用 stream_knobs 合并规则（单点维护）。"""
    from engram.backend.app.gateway.stream_knobs import (
        apply_stream_knobs,
        knobs_from_cli_state,
    )

    configurable: dict = {}
    loop = apply_stream_knobs(
        configurable, knobs_from_cli_state({"max_loop_steps": 7, "skill_override": ["x"]}),
    )
    assert loop == 7
    assert configurable["skill_override"] == ["x"]