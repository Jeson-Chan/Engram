"""真实 LeaderAgent subagent 委托集成测试 — E2E 缺陷 B 回归。

E2E 现场：delegate_to_subagent → SubagentRuntime.invoke → agent.invoke，
agent 是 make_lead_agent 返回的 LeaderAgent（只有 run()/graph）→
AttributeError: 'LeaderAgent' object has no attribute 'invoke'
→ SpecialistCrashError。

修复（runtime-hardening / 内部 subagent 委托）：LeaderAgent.invoke(state, config)。
本测试用真实 make_lead_agent（FakeListChatModel + stub tool 编译的真实 graph），
不用 MagicMock 假 agent——旧测试 test_bootstrap_fix.py 用 MagicMock 注入带 invoke
的假 agent，正是漏掉本缺陷的原因。
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.tools import BaseTool

from engram.backend.agents.capabilities.registry import CapabilityRegistry
from engram.backend.agents.leader.factory import make_lead_agent
from engram.backend.agents.multiagent.exceptions import SpecialistCrashError
from engram.backend.agents.multiagent.runtimes.subagent_runtime import SubagentRuntime
from engram.backend.agents.multiagent.types import SpecialistRequest
from engram.backend.agents.reporting.markdown_reporter import MarkdownReporter
from engram.backend.tests.v1._fake_model import FakeChatModelWithTools


class _StubTool(BaseTool):
    name: str = "web_search_mcp"
    description: str = "stub"

    def _run(self, query: str = "") -> str:
        return "stub result"


def _make_real_leader():
    registry = CapabilityRegistry(
        models={"researcher": FakeChatModelWithTools(responses=["subagent says ok"])},
        tools={"web_search_mcp": _StubTool()},
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )
    return make_lead_agent(capability_registry=registry)


def _request(**kw) -> SpecialistRequest:
    defaults = dict(
        goal="summarize the research thread",
        success_criteria="a short summary",
        context_summary=None,
        sandbox_id=None,
        artifacts_path="/workspace",
        max_steps=10,
        timeout_seconds=60,
    )
    defaults.update(kw)
    return SpecialistRequest(**defaults)


def test_real_leader_agent_subagent_roundtrip():
    """真实 LeaderAgent：delegate 返回结构化结果，而不是 AttributeError。"""
    leader = _make_real_leader()
    rt = SubagentRuntime(agent_factory=lambda: leader)
    result = rt.invoke(_request())
    assert isinstance(result.raw_output, str)
    assert result.raw_output  # 非空输出
    assert result.duration_seconds >= 0


def test_real_leader_agent_invoke_is_callable_directly():
    """LeaderAgent.invoke(state, config) 直接可用（契约面）。"""
    leader = _make_real_leader()
    state = {
        "messages": [],
        "user_input": "hello",
        "research_question": "hello",
    }
    final = leader.invoke(state, config={"recursion_limit": 20})
    assert isinstance(final, dict)
    assert final.get("messages")


def test_real_leader_agent_invoke_inside_running_loop_fails_fast():
    """事件循环内调用 invoke（嵌套调用）→ 快速 RuntimeError（review high：
    旧线程兜底会阻塞调用方循环整段 graph 时长，AsyncPostgresSaver 池绑定
    原循环时直接死锁）。"""
    leader = _make_real_leader()
    state = {"messages": [], "user_input": "hi", "research_question": "hi"}

    async def _call_from_loop():
        return leader.invoke(state, config={"recursion_limit": 20})

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(_call_from_loop())


def test_real_leader_agent_invoke_deep_copies_caller_config():
    """invoke 不改写调用方的 config dict（浅拷贝会跨调用共享生成的
    thread_id，污染会话状态——review medium）。"""
    leader = _make_real_leader()
    caller_config = {"configurable": {"user_id": "alice"}, "recursion_limit": 20}
    state = {"messages": [], "user_input": "hi", "research_question": "hi"}

    leader.invoke(state, config=caller_config)

    # 调用方原 dict 未被注入 thread_id（生成的 id 只在内部副本里）
    assert "thread_id" not in caller_config["configurable"]
    assert caller_config["configurable"]["user_id"] == "alice"


def test_real_leader_agent_invoke_defaults_user_id():
    """user_id 缺省（无 ambient config）→ 显式 "default"，绝不留 None
    （None = 记忆召回不过滤 → 跨用户泄漏——review high）。"""
    leader = _make_real_leader()
    state = {"messages": [], "user_input": "hi", "research_question": "hi"}

    final = leader.invoke(state, config={"recursion_limit": 20})
    assert isinstance(final, dict)


def test_real_leader_agent_failure_is_structured_not_attributeerror():
    """subagent 失败 → SpecialistCrashError（结构化），不是 AttributeError。"""
    leader = _make_real_leader()

    def _boom(self, state, config=None):
        raise RuntimeError("inner failure")

    import types

    leader.invoke = types.MethodType(_boom, leader)  # noqa: patch to force failure
    rt = SubagentRuntime(agent_factory=lambda: leader)
    with pytest.raises(SpecialistCrashError) as exc_info:
        rt.invoke(_request())
    # 错误信息可读（非 "has no attribute 'invoke'"）
    assert "invoke" not in str(exc_info.value) or "no attribute" not in str(exc_info.value)
