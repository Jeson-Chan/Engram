"""Checkpoint 兼容性回归 — E2E 缺陷 I（runtime-hardening）。

E2E 现场：读取历史 thread 时日志出现
`Deserializing unregistered type engram.backend.agents.state.types.AgentError
from checkpoint. This will be blocked in a future version.`

修复（design.md 决策 8）：create_pg_checkpointer 的 serde 走构造器
`allowed_msgpack_modules=_engram_state_types()`（engram.backend.agents.state.types
模块内定义的状态类；with_msgpack_allowlist() 在默认 permissive 基座上是
no-op，必须走构造器）。

验证：
- 旧 checkpoint 字节（默认序列化器产物）经 allowlist serde 反序列化成功
- 全程无 "unregistered" 告警（告警按 (module, class) 进程级去重，测试逐例清空）
- 严格模式（LANGGRAPH_STRICT_MSGPACK=true）：默认 serde 把 AgentError
  降级为裸 dict（静默损坏）；显式 allowlist 仍反序列化为 AgentError
- allowlist 只覆盖 engram 状态模块
"""

from __future__ import annotations

import logging

import pytest
from langchain_core.messages import AIMessage

from engram.backend.agents.runtime.pg_checkpointer import _engram_state_types
from engram.backend.agents.state.types import AgentError, Observation, Source


def _legacy_typed(obj):
    """旧 checkpoint 字节：默认序列化器（无 allowlist）的产物。"""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer().dumps_typed(obj)


def _allowlisted_serde():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=_engram_state_types())


@pytest.fixture()
def _fresh_warnings(caplog):
    """清空 jsonplus 的进程级告警去重，使每例断言独立。"""
    from langgraph.checkpoint.serde.jsonplus import _warned_unregistered_types

    _warned_unregistered_types.clear()
    caplog.set_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus")
    return caplog


class TestAllowlistedRoundtrip:
    def test_agent_error_roundtrip_without_warning(self, _fresh_warnings):
        err = AgentError(error_id="e1", stage="plan", message="boom")
        serde = _allowlisted_serde()
        loaded = serde.loads_typed(_legacy_typed(err))
        assert isinstance(loaded, AgentError)
        assert loaded.message == "boom"
        assert not [
            r for r in _fresh_warnings.records
            if "unregistered" in r.getMessage() or "Blocked" in r.getMessage()
        ], "allowlist 路径不得出现未注册类型/拦截告警"

    def test_default_serializer_warns_on_agent_error(self, _fresh_warnings):
        """缺陷复现：默认 serde 反序列化 AgentError 产生 unregistered 告警。"""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        err = AgentError(error_id="e2", stage="tool", message="x")
        serde = JsonPlusSerializer()
        loaded = serde.loads_typed(_legacy_typed(err))
        assert type(loaded) is AgentError  # permissive：warn 但放行
        assert any(
            "unregistered" in r.getMessage() for r in _fresh_warnings.records
        ), "默认路径应复现 E2E 告警"

    def test_other_state_types_roundtrip(self, _fresh_warnings):
        serde = _allowlisted_serde()
        obs = Observation(observation_id="o1", step_id="s1", content="观察")
        loaded_obs = serde.loads_typed(_legacy_typed(obs))
        assert type(loaded_obs) is Observation

        src = Source(source_id="src1", url="https://x", title="t")
        loaded_src = serde.loads_typed(_legacy_typed(src))
        assert type(loaded_src) is Source

    def test_allowlist_covers_state_module_only(self):
        """覆盖全部会进 ThreadState 的状态模块（review medium：multiagent.types
        的 ArtifactRef 等也被冻结进 checkpoint）。"""
        classes = _engram_state_types()
        modules = {c.__module__ for c in classes}
        assert modules == {
            "engram.backend.agents.state.types",
            "engram.backend.agents.multiagent.types",
        }
        assert AgentError in classes

    def test_langchain_messages_still_safe(self, _fresh_warnings):
        serde = _allowlisted_serde()
        msg = AIMessage(content="hi")
        loaded = serde.loads_typed(_legacy_typed(msg))
        assert isinstance(loaded, AIMessage)


class TestStrictModeCompat:
    """严格模式开关在导入期读 env（模块级常量），测试直接 patch 模块属性。"""

    @pytest.fixture()
    def _strict(self, monkeypatch):
        import langgraph.checkpoint.serde.jsonplus as jsonplus_mod

        monkeypatch.setattr(jsonplus_mod._lg_msgpack, "STRICT_MSGPACK_ENABLED", True)

    def test_strict_default_degrades_agent_error_to_dict(self, _strict, _fresh_warnings):
        """严格模式 + 默认 serde：AgentError 被拦截降级为 dict（静默损坏）。"""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        err = AgentError(error_id="e3", stage="plan", message="degraded")
        typed = JsonPlusSerializer(allowed_msgpack_modules=True).dumps_typed(err)

        strict_default = JsonPlusSerializer()  # 构造时 strict → None allowlist
        loaded = strict_default.loads_typed(typed)
        assert not isinstance(loaded, AgentError)  # 降级（dict/裸值）
        assert any("Blocked" in r.getMessage() for r in _fresh_warnings.records)

    def test_explicit_allowlist_survives_strict_mode(self, _strict, _fresh_warnings):
        """严格模式 + 显式 allowlist：AgentError 完整反序列化（前向兼容语义）。"""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        err = AgentError(error_id="e4", stage="plan", message="strict ok")
        typed = JsonPlusSerializer(allowed_msgpack_modules=True).dumps_typed(err)

        serde = _allowlisted_serde()
        loaded = serde.loads_typed(typed)
        assert isinstance(loaded, AgentError)
        assert loaded.message == "strict ok"
        assert not [
            r for r in _fresh_warnings.records
            if "unregistered" in r.getMessage() or "Blocked" in r.getMessage()
        ]
