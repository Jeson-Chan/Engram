from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import BaseTool

from engram.backend.agents.capabilities.registry import CapabilityRegistry
from engram.backend.agents.leader.agent import LeaderAgent
from engram.backend.agents.leader.factory import make_lead_agent
from engram.backend.agents.reporting.markdown_reporter import MarkdownReporter


class _StubTool(BaseTool):
    name: str = "web_search_mcp"
    description: str = "stub"

    def _run(self, query: str = "") -> str:
        return "stub result"


def _fake_model() -> FakeListChatModel:
    return FakeListChatModel(responses=["ok"])


def _registry(with_tool: bool = True) -> CapabilityRegistry:
    tools = {"web_search_mcp": _StubTool()} if with_tool else {}
    return CapabilityRegistry(
        models={"researcher": _fake_model()},
        tools=tools,
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )


def test_make_lead_agent_returns_leader_agent_with_graph() -> None:
    registry = _registry()
    agent = make_lead_agent(capability_registry=registry, middleware_manager=None)
    assert isinstance(agent, LeaderAgent)
    assert agent.graph is not None
    assert agent.capability_registry is registry


def test_make_lead_agent_via_runnable_config() -> None:
    registry = _registry()
    config = {"configurable": {"expert_mode": True, "capability_registry": registry}}
    agent = make_lead_agent(runnable_config=config)
    assert isinstance(agent, LeaderAgent)


def test_make_lead_agent_raises_without_registry() -> None:
    import pytest

    with pytest.raises(ValueError, match="capability_registry is required"):
        make_lead_agent()


def test_make_lead_agent_no_tools_still_works() -> None:
    registry = _registry(with_tool=False)
    agent = make_lead_agent(capability_registry=registry)
    assert isinstance(agent, LeaderAgent)
    assert agent.graph is not None


def test_make_lead_agent_expert_mode_param() -> None:
    """expert_mode=True 参数应装配激进 middleware（Todo enforce_completion=True）。"""
    registry = _registry()
    agent = make_lead_agent(expert_mode=True, capability_registry=registry)
    assert isinstance(agent, LeaderAgent)
    # graph 编译应成功，含 checkpointer


def test_make_lead_agent_default_mode_param() -> None:
    """expert_mode=False 参数应装配温和 middleware（Todo enforce_completion=False）。"""
    registry = _registry()
    agent = make_lead_agent(expert_mode=False, capability_registry=registry)
    assert isinstance(agent, LeaderAgent)
    assert agent.graph is not None


# ── subagent 事件循环 bug 回归（delegate_to_subagent 跨循环崩溃修复） ──

def test_make_lead_agent_explicit_checkpointer_overrides_global() -> None:
    """显式 checkpointer 参数覆盖全局单例（subagent 注入 InMemorySaver）。

    回归背景：delegate_to_subagent 经 LeaderAgent.invoke 的 asyncio.run
    在新循环跑子 graph；全局 AsyncPostgresSaver 的池/TTL Event 绑定主循环，
    跨循环 await 崩溃。修复 = 子 agent factory 传独立 InMemorySaver。
    这里锁行为契约：显式传了就编译成功（create_agent 用它），不传则回落
    全局单例（现有调用方行为不变）。
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from engram.backend.agents.runtime import checkpointer as cp_mod

    # 全局槽位预装一个可识别的 saver（模拟 lifespan 预装 AsyncPostgresSaver）
    cp_mod.set_checkpointer(InMemorySaver())
    try:
        # 显式传入 → 子 agent 路径（独立 saver，不触全局）
        agent = make_lead_agent(
            capability_registry=_registry(),
            checkpointer=InMemorySaver(),
        )
        assert isinstance(agent, LeaderAgent)
        assert agent.graph is not None
        # 未传 → 回落全局单例（现有调用方行为不变）
        agent_default = make_lead_agent(capability_registry=_registry())
        assert isinstance(agent_default, LeaderAgent)
        assert agent_default.graph is not None
    finally:
        cp_mod.reset_checkpointer()
