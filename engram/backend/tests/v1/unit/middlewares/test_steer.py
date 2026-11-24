"""real-steer — SteerQueues + SteerMiddleware 单测。"""
from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from engram.backend.agents.middlewares.steer_middleware import SteerMiddleware
from engram.backend.agents.middlewares.steer_queue import SteerQueues


def test_put_drain_thread_isolation() -> None:
    q = SteerQueues()
    assert q.put("t1", "先查 A") is True
    assert q.put("t1", "再查 B") is True
    assert q.put("t2", "别的线程") is True
    assert q.drain("t1") == ["先查 A", "再查 B"]
    assert q.drain("t1") == []  # drain 即消费
    assert q.drain("t2") == ["别的线程"]


def test_put_empty_ignored() -> None:
    q = SteerQueues()
    assert q.put("t1", "   ") is False
    assert q.drain("t1") == []


def test_clear_drops_residual() -> None:
    q = SteerQueues()
    q.put("t1", "迟到的话")
    q.clear("t1")
    assert q.drain("t1") == []


def _mw(queues: SteerQueues) -> SteerMiddleware:
    return SteerMiddleware(queues)


def _runtime(thread_id: str = "t1", journal=None) -> SimpleNamespace:
    return SimpleNamespace(context={"thread_id": thread_id, "run_id": "r1", "journal": journal})


def test_before_model_injects_human_messages() -> None:
    q = SteerQueues()
    q.put("t1", "补充：只看 2024 年")
    q.put("t1", "别用 web_search")
    result = _mw(q).before_model({"user_input": "原任务"}, _runtime())
    assert result is not None
    msgs = result["messages"]
    assert len(msgs) == 2
    assert all(isinstance(m, HumanMessage) for m in msgs)
    assert msgs[0].content == "补充：只看 2024 年"
    assert q.drain("t1") == []  # 注入即消费


def test_before_model_empty_queue_returns_none() -> None:
    assert _mw(SteerQueues()).before_model({}, _runtime()) is None


def test_before_model_no_thread_id_returns_none() -> None:
    q = SteerQueues()
    q.put("t1", "x")
    assert _mw(q).before_model({}, SimpleNamespace(context={})) is None


def test_journal_and_injection_recorded() -> None:
    class _Journal:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        def append(self, etype: str, payload: dict) -> None:
            self.events.append((etype, payload))

    j = _Journal()
    q = SteerQueues()
    q.put("t1", "插话")
    _mw(q).before_model({}, _runtime(journal=j))
    assert len(j.events) == 1
    assert j.events[0][0] == "steer.injected"
    assert j.events[0][1]["text"] == "插话"


def test_after_agent_clears_residual() -> None:
    q = SteerQueues()
    q.put("t1", "迟到的插话")
    _mw(q).after_agent({}, _runtime())
    assert q.drain("t1") == []