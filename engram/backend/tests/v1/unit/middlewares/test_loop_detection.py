from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engram.backend.agents.middlewares.loop_detection_middleware import (
    LoopDetectionConfig,
    LoopDetectionMiddleware,
    _detect_loop,
    _hash_args,
)


def _ai_with_tool(name: str, args: dict, content: str = "") -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[{"name": name, "args": args, "id": f"call-{name}-{args}", "type": "tool_call"}],
    )


def test_hash_args_stable() -> None:
    assert _hash_args({"a": 1, "b": 2}) == _hash_args({"b": 2, "a": 1})


def test_hash_args_truncates_long() -> None:
    long_args = {"q": "x" * 200}
    h = _hash_args(long_args)
    assert len(h) <= 100


def test_detect_loop_returns_none_when_no_repeats() -> None:
    msgs = [
        _ai_with_tool("web_search", {"query": "a"}),
        _ai_with_tool("web_search", {"query": "b"}),
    ]
    assert _detect_loop(msgs, window=10, threshold=3) is None


def test_detect_loop_returns_tool_when_threshold_hit() -> None:
    msgs = [
        _ai_with_tool("web_search", {"query": "北京天气"}),
        _ai_with_tool("web_search", {"query": "北京天气"}),
        _ai_with_tool("web_search", {"query": "北京天气"}),
    ]
    assert _detect_loop(msgs, window=10, threshold=3) == "web_search"


def test_detect_loop_different_args_not_triggered() -> None:
    msgs = [
        _ai_with_tool("web_search", {"query": "北京"}),
        _ai_with_tool("web_search", {"query": "上海"}),
        _ai_with_tool("web_search", {"query": "广州"}),
    ]
    assert _detect_loop(msgs, window=10, threshold=3) is None


def test_detect_loop_window_limits_scan() -> None:
    # 5 条历史 + window=3 只扫最后 3 条，早期重复不计
    msgs = [
        _ai_with_tool("web_search", {"query": "x"}),
        _ai_with_tool("web_search", {"query": "x"}),
        _ai_with_tool("browse", {"url": "y"}),
        _ai_with_tool("browse", {"url": "y"}),
    ]
    # window=4 看到全部 4 条，web_search x2 + browse x2，threshold=3 都不触发
    assert _detect_loop(msgs, window=4, threshold=3) is None


def test_middleware_disabled_returns_none() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(enabled=False))
    state = {"messages": [_ai_with_tool("web_search", {"q": "x"})] * 3}
    assert mw.after_model(state, runtime=None) is None


def test_middleware_no_loop_returns_none() -> None:
    mw = LoopDetectionMiddleware()
    state = {"messages": [_ai_with_tool("web_search", {"q": "a"}), _ai_with_tool("web_search", {"q": "b"})]}
    assert mw.after_model(state, runtime=None) is None


def test_middleware_loop_clears_tool_calls_and_jumps() -> None:
    mw = LoopDetectionMiddleware()
    state = {
        "messages": [
            _ai_with_tool("web_search", {"query": "x"}),
            _ai_with_tool("web_search", {"query": "x"}),
            _ai_with_tool("web_search", {"query": "x"}),
        ]
    }
    result = mw.after_model(state, runtime=None)
    assert result is not None
    assert result.get("jump_to") == "model"
    msgs = result.get("messages", [])
    assert len(msgs) == 2
    # 第一条是清空 tool_calls 的 AIMessage
    cleared = msgs[0]
    assert isinstance(cleared, AIMessage)
    assert cleared.tool_calls == []
    assert cleared.additional_kwargs.get("loop_detected") == "web_search"
    # 第二条是引导 HumanMessage
    assert isinstance(msgs[1], HumanMessage)
    assert msgs[1].name == "loop_detection"
    assert "web_search" in msgs[1].content


def test_middleware_loop_reuses_id_for_pairing() -> None:
    """Regression: cleared AIMessage must reuse original id so add_messages
    replaces (not appends). Otherwise the original tool_calls-bearing AIMessage
    stays in history; jump_to model skips ToolNode → no ToolMessage → 400
    'insufficient tool messages following tool_calls' on next model call."""
    mw = LoopDetectionMiddleware()
    last_ai = AIMessage(
        id="ai-original-id",
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "tc1", "type": "tool_call"}],
        additional_kwargs={"tool_calls": [{"name": "web_search", "args": {"query": "x"}, "id": "tc1"}]},
    )
    state = {"messages": [_ai_with_tool("web_search", {"query": "x"}), _ai_with_tool("web_search", {"query": "x"}), last_ai]}
    result = mw.after_model(state, runtime=None)
    assert result is not None
    cleared = result["messages"][0]
    assert isinstance(cleared, AIMessage)
    # id 复用 → add_messages 替换原消息，非追加
    assert cleared.id == "ai-original-id"
    # additional_kwargs 里陈旧 tool_calls 必须剥掉，防 _has_tool_call_intent 误判
    assert "tool_calls" not in (cleared.additional_kwargs or {})
    assert cleared.tool_calls == []
    assert cleared.additional_kwargs.get("loop_detected") == "web_search"


def test_middleware_no_tool_calls_on_last_ai_returns_none() -> None:
    mw = LoopDetectionMiddleware()
    # 最后一条 AIMessage 无 tool_calls（模型想退出），即使历史有重复也不熔断
    state = {
        "messages": [
            _ai_with_tool("web_search", {"q": "x"}),
            _ai_with_tool("web_search", {"q": "x"}),
            _ai_with_tool("web_search", {"q": "x"}),
            AIMessage(content="最终答案", tool_calls=[]),
        ]
    }
    assert mw.after_model(state, runtime=None) is None


# ── 单工具过搜预算（2026-11-20 线上 60 次 web_search 深挖型循环回归） ──────


def _runtime(tid: str = "t1", rid: str = "r1") -> SimpleNamespace:
    return SimpleNamespace(context={"thread_id": tid, "run_id": rid})


def _request(name: str = "web_search", call_id: str = "tc1") -> SimpleNamespace:
    return SimpleNamespace(
        tool_call={"name": name, "id": call_id, "args": {"query": call_id}},
        runtime=_runtime(),
        state={"messages": [], "errors": []},
    )


def _ok_result(call_id: str = "tc1", name: str = "web_search") -> ToolMessage:
    return ToolMessage(content='{"results": []}', tool_call_id=call_id, name=name)


def test_search_soft_limit_queues_stop_guidance() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(per_tool_soft_limit=2, per_tool_hard_limit=5))
    for i in range(2):
        req = _request(call_id=f"tc{i}")
        mw.wrap_tool_call(req, lambda r: _ok_result(r.tool_call["id"]))

    result = mw.before_model({}, _runtime())
    assert result is not None
    msg = result["messages"][0]
    assert isinstance(msg, HumanMessage)
    assert msg.name == "loop_detection"
    assert "web_search" in msg.content
    # 只提醒一次（队列 drain 后为空）
    assert mw.before_model({}, _runtime()) is None


def test_search_hard_limit_clears_tool_calls_and_jumps_model() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(per_tool_soft_limit=99, per_tool_hard_limit=2))
    for i in range(2):
        req = _request(call_id=f"tc{i}")
        mw.wrap_tool_call(req, lambda r: _ok_result(r.tool_call["id"]))

    last_ai = AIMessage(
        id="ai-hard",
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "new"}, "id": "tcz", "type": "tool_call"}],
    )
    result = mw.after_model({"messages": [last_ai]}, _runtime())
    assert result is not None
    assert result["jump_to"] == "model"
    cleared = result["messages"][0]
    assert isinstance(cleared, AIMessage)
    assert cleared.tool_calls == []
    assert cleared.additional_kwargs.get("loop_detected") == "web_search"
    assert "上限" in result["messages"][1].content


def test_search_calls_beyond_hard_limit_are_blocked() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(per_tool_soft_limit=99, per_tool_hard_limit=1))
    mw.wrap_tool_call(_request(call_id="tc1"), lambda r: _ok_result("tc1"))

    executed = False

    def handler(request):
        nonlocal executed
        executed = True
        return _ok_result("tc2")

    result = mw.wrap_tool_call(_request(call_id="tc2"), handler)
    assert executed is False
    assert result is not None
    assert result.update["messages"][0].status == "error"


def test_search_hard_limit_forces_final_answer_when_model_ignores_twice() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(
        per_tool_soft_limit=99, per_tool_hard_limit=1, max_forced_finalizations=1,
    ))
    mw.wrap_tool_call(_request(call_id="tc1"), lambda r: _ok_result("tc1"))
    ai = AIMessage(
        id="ai-ignore",
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "again"}, "id": "tc9", "type": "tool_call"}],
    )
    state = {"messages": [ai], "sources": [{"url": "https://example.com/a"}]}

    first = mw.after_model(state, _runtime())
    assert first is not None and first["jump_to"] == "model"

    second = mw.after_model(state, _runtime())
    assert second is not None
    assert second["jump_to"] == "end"
    final = second["messages"][0]
    assert isinstance(final, AIMessage)
    assert "达到循环保护上限" in final.content
    assert "https://example.com/a" in final.content


def test_before_agent_resets_counts_for_new_invocation() -> None:
    """同一 thread 的新一轮 invocation 从 0 计数（run_id 缺失也不会跨轮累计）。"""
    mw = LoopDetectionMiddleware(LoopDetectionConfig(per_tool_soft_limit=99, per_tool_hard_limit=2))
    mw.wrap_tool_call(_request(call_id="tc1"), lambda r: _ok_result("tc1"))
    mw.wrap_tool_call(_request(call_id="tc2"), lambda r: _ok_result("tc2"))
    assert mw._saturated_tool(_runtime()) == ("web_search", 2)

    mw.before_agent({}, _runtime())
    assert mw._saturated_tool(_runtime()) is None


def test_non_search_tools_are_not_budgeted() -> None:
    mw = LoopDetectionMiddleware(LoopDetectionConfig(per_tool_soft_limit=1, per_tool_hard_limit=1))
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return ToolMessage(content="ok", tool_call_id=request.tool_call["id"], name="bash")

    for i in range(3):
        mw.wrap_tool_call(_request(name="bash", call_id=f"b{i}"), handler)

    assert calls == 3
    assert mw.before_model({}, _runtime()) is None
