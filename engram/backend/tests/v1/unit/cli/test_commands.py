"""commands.py / 命令测试：/expert /default /report pending 标记。"""

from io import StringIO

from rich.console import Console

from engram.backend.app.cli.commands import handle_command


def _make_console() -> Console:
    return Console(file=StringIO(), width=120)


def _make_state() -> dict:
    return {"pending_expert_mode": None, "pending_report": None}


def test_expert_sets_pending_true() -> None:
    state = _make_state()
    handle_command("/expert", _make_console(), None, state, runtime=None)
    assert state["pending_expert_mode"] is True


def test_default_sets_pending_false() -> None:
    state = _make_state()
    handle_command("/default", _make_console(), None, state, runtime=None)
    assert state["pending_expert_mode"] is False


def test_report_no_topic_sets_pending_empty_string() -> None:
    """/report 无 topic → pending_report=""（空字符串表无 topic，区别于 None 未设）。"""
    state = _make_state()
    handle_command("/report", _make_console(), None, state, runtime=None)
    assert state["pending_report"] == ""


def test_report_with_topic_sets_pending_topic() -> None:
    state = _make_state()
    handle_command("/report 天气调研", _make_console(), None, state, runtime=None)
    assert state["pending_report"] == "天气调研"


def test_help_does_not_set_pending() -> None:
    state = _make_state()
    handle_command("/help", _make_console(), None, state, runtime=None)
    assert state["pending_expert_mode"] is None
    assert state["pending_report"] is None


def test_exit_removed() -> None:
    """退出统一走 Ctrl+C（tui-command-surface）：/exit 不存在。"""
    state = _make_state()
    assert handle_command("/exit", _make_console(), None, state, runtime=None) is False


def test_quit_alias_removed() -> None:
    """`/quit` 已弃用（tui-interactive-fixes）：`/exit` 亦于 tui-command-surface 移除。"""
    state = _make_state()
    assert handle_command("/quit", _make_console(), None, state, runtime=None) is False


def test_clear_removed() -> None:
    """清屏统一走 Ctrl+L（tui-command-surface）：/clear 不存在。"""
    state = _make_state()
    assert handle_command("/clear", _make_console(), None, state, runtime=None) is False


def test_guide_sets_pending() -> None:
    """-/guide：设 pending_guide 标记（TUI 消费打开向导）。"""
    state = _make_state()
    handle_command("/guide", _make_console(), None, state, runtime=None)
    assert state["pending_guide"] is True


def test_unknown_command_returns_false() -> None:
    state = _make_state()
    assert handle_command("/unknown", _make_console(), None, state, runtime=None) is False


# ---- runtime-knobs：/rounds /effort /window ----

def _knob_state() -> dict:
    return {"max_loop_steps": None, "reasoning_effort": None, "context_window": None}


def test_rounds_sets_and_validates() -> None:
    state = _knob_state()
    handle_command("/rounds 10", _make_console(), None, state, runtime=None)
    assert state["max_loop_steps"] == 10
    handle_command("/rounds 0", _make_console(), None, state, runtime=None)
    assert state["max_loop_steps"] == 10  # 非法值不改
    handle_command("/rounds abc", _make_console(), None, state, runtime=None)
    assert state["max_loop_steps"] == 10


def test_rounds_off_clears() -> None:
    state = _knob_state()
    state["max_loop_steps"] = 7
    handle_command("/rounds off", _make_console(), None, state, runtime=None)
    assert state["max_loop_steps"] is None


def test_effort_sets_and_clears() -> None:
    state = _knob_state()
    handle_command("/effort medium", _make_console(), None, state, runtime=None)
    assert state["reasoning_effort"] == "medium"
    handle_command("/effort extreme", _make_console(), None, state, runtime=None)
    assert state["reasoning_effort"] == "medium"  # 非法档位不改
    handle_command("/effort off", _make_console(), None, state, runtime=None)
    assert state["reasoning_effort"] is None


def test_window_sets_and_clears() -> None:
    state = _knob_state()
    handle_command("/window 32000", _make_console(), None, state, runtime=None)
    assert state["context_window"] == 32_000
    handle_command("/window 999", _make_console(), None, state, runtime=None)
    assert state["context_window"] == 32_000  # 低于下限不改
    handle_command("/window off", _make_console(), None, state, runtime=None)
    assert state["context_window"] is None
