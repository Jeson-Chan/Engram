"""工具失败分类回归 — 长成功结果里的 "blocked/403" 不能算失败。

线上 2026-11-20：一次 run 的 5 次 web_search 被标记 blocked，实际是成功的
搜索结果正文里引用了 "blocked" 字样。ToolCallMiddleware 之前对整个结果文本
（且未拆 Command 包装）跑 _BLOCKED_RE，导致假失败。
"""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from engram.backend.agents.middlewares.tool_call_middleware import (
    _classify_business_failure,
    _is_failure,
    _result_text,
)


def test_long_successful_search_with_blocked_word_is_not_failure() -> None:
    payload = json.dumps({
        "query": "SWE-bench leaderboard",
        "backend": "tavily",
        "results": [
            {"title": "Benchmark report", "url": "https://example.com", "content": "This page was blocked in 2024, " + "x" * 2500},
        ],
    })
    assert _classify_business_failure(payload) is None
    tool_msg = ToolMessage(content=payload, tool_call_id="tc1", name="web_search")
    assert _is_failure(tool_msg) is None


def test_short_blocked_error_still_detected() -> None:
    assert _classify_business_failure("403 Access denied") == "blocked"


def test_empty_error_payload_still_detected() -> None:
    assert _classify_business_failure('{"error": "No results found"}') == "empty"


def test_command_result_is_unwrapped_before_classification() -> None:
    tool_msg = ToolMessage(
        content='{"error": "No results found", "query": "x"}',
        tool_call_id="tc1",
        name="web_search",
    )
    command = Command(update={"messages": [tool_msg], "observations": [], "sources": []})
    assert _result_text(command).startswith('{"error"')
    assert _is_failure(command) == ("empty", "无搜索结果")


def test_long_command_result_with_blocked_reference_is_not_failure() -> None:
    tool_msg = ToolMessage(
        content=json.dumps({
            "results": [{"content": "page was blocked " + "y" * 2500}],
        }),
        tool_call_id="tc1",
        name="web_search",
    )
    command = Command(update={"messages": [tool_msg]})
    assert _is_failure(command) is None