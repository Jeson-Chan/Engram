from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from engram.backend.agents.capabilities.registry import CapabilityRegistry


def _last_ai_message(state: Any) -> str:
    """从 state.messages 取最后一条 AIMessage 的文本内容（default 模式输出）。"""
    messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    item["text"] if isinstance(item, dict) and "text" in item else str(item)
                    for item in content
                    if item
                ]
                return "".join(parts)
    return ""


def _ambient_config_value(key: str) -> Any:
    """读当前 LangGraph runnable config 的 configurable 值（不在 runnable
    上下文时返 None）。与记忆中间件同款 get_config() 语义——subagent 从
    ambient 继承 user_id 用。
    """
    try:
        from langgraph.config import get_config

        config = get_config()
    except RuntimeError:
        return None
    except Exception:
        return None
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable") or {}
    return configurable.get(key) if isinstance(configurable, dict) else None


def _resolve_actual_model_name(registry: CapabilityRegistry) -> str:
    """取实际 researcher 模型的路由 provider 名（FallbackChatModel.provider_names）。

    优于 config 静态 researcher_model（可能是 fake-researcher），反映真实路由链。
    FallbackChatModel 的 _identifying_params 含 providers + active，取 provider_names。
    """
    try:
        model = registry.get_model("researcher")
        # FallbackChatModel 有 provider_names
        names = getattr(model, "provider_names", None)
        if names:
            return ",".join(names)
        # 普通模型无 provider_names，回退 identifying_params 或 model 名
        params = getattr(model, "_identifying_params", None)
        if callable(params):
            params = params()
        if isinstance(params, dict) and params.get("model"):
            return str(params["model"])
        return getattr(model, "model", "") or str(type(model).__name__)
    except Exception:
        return "unknown"
from engram.backend.agents.state.thread_state import create_initial_thread_state


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    thread_id: str
    final_report: str
    events_path: str
    artifact_path: str | None
    state: dict[str, Any]


@dataclass
class LeaderAgent:
    """Thin shell: invokes compiled graph + collects report + saves artifact.

    ReAct intelligence (multi-turn decisions, tool calls, exit logic) lives
    inside the graph via create_agent + AgentMiddleware. This class only does
    graph.ainvoke() + reporter + artifact + outer config wiring. All logging
    is handled by RunJournalMiddleware inside the graph.
    """

    graph: Any
    capability_registry: CapabilityRegistry

    def invoke(self, state: Any, config: dict | None = None) -> Any:
        """同步兼容入口 — SubagentRuntime.invoke 委托目标（E2E 缺陷 B）。

        设计决策（web-tui-research-workbench design.md §8）：LeaderAgent 暴露
        invoke(state, config)，保留 run() 调用方与测试不动。委托目标是
        graph.ainvoke（而非 graph.invoke）——MCP tools 是 async-only
        StructuredTool，同步 invoke 在 MCP 启用时会失败。

        两种调用上下文：
        - 无运行循环（同步工具在线程池执行器里被 ToolNode 调用）→
          asyncio.run(ainvoke)
        - 已在事件循环内（review high）：不再"新线程 + .result() 阻塞"——
          那会卡死事件循环整段 graph 时长，且 AsyncPostgresSaver 的池绑定
          原循环会真死锁。嵌套循环是编程错误：快速抛 RuntimeError。

        Config 归属（review high/medium）：
        - 深拷贝 configurable（浅拷贝会改写调用方的 dict——跨调用共享了
          第一个生成的 thread_id，污染会话状态）
        - thread_id 缺省 → 每调用独立生成（隔离上下文）
        - user_id 从 ambient runnable config 继承（get_config）；无则显式
          "default"——绝不留 None：记忆隔离链（MemoryQuery.user_id=None =
          不过滤）会把其它用户记忆泄进 subagent 上下文（跨用户泄漏）。
        """
        effective_config = dict(config or {})
        # 深拷贝 configurable：调用方的 dict 不被就地改写
        configurable = dict(effective_config.get("configurable") or {})
        effective_config["configurable"] = configurable
        if not configurable.get("thread_id"):
            import uuid

            configurable["thread_id"] = uuid.uuid4().hex
        if not configurable.get("user_id"):
            ambient_user = _ambient_config_value("user_id")
            configurable["user_id"] = ambient_user or "default"

        async def _ainvoke() -> Any:
            return await self.graph.ainvoke(state, config=effective_config)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_ainvoke())
        # 已在事件循环内（嵌套调用）：编程错误，快速失败（不阻塞循环等死锁）
        raise RuntimeError(
            "LeaderAgent.invoke called from a running event loop; "
            "subagent delegation must run from a sync (tool-executor) context"
        )

    def run(self, question: str, run_context: Any) -> AgentRunResult:
        initial = create_initial_thread_state(question)
        initial["research_question"] = question
        initial["metadata"] = {"expert_mode": run_context.config.runtime.expert_mode}

        config = {
            "configurable": {
                "expert_mode": run_context.config.runtime.expert_mode,
                "run_id": run_context.run_id,
                "thread_id": run_context.thread_id,
                "journal": run_context.journal,
                "output_dir": str(run_context.output_dir),
                "plan_enabled": run_context.config.runtime.plan_enabled,
                "timezone": run_context.config.runtime.timezone,
                # 取实际模型的路由 provider 名（FallbackChatModel 的 provider_names），非 config 静态值
                "model": _resolve_actual_model_name(self.capability_registry),
            },
            # recursion_limit 从 config 推导：max_loop_steps * graph_node_multiplier。
            # 不再硬编码——让长程任务有足够图节点预算，安全网是 StallDetectionMiddleware。
            "recursion_limit": run_context.config.runtime.max_loop_steps * run_context.config.runtime.graph_node_multiplier,
        }

        # MCP tools are async-only StructuredTool; graph must run in async mode.
        async def _ainvoke_with_fallback() -> tuple[dict[str, Any], bool]:
            try:
                state = await self.graph.ainvoke(
                    {
                        "messages": [HumanMessage(content=question)],
                        "user_input": question,
                        "research_question": question,
                    },
                    config=config,
                )
                return state, False
            except GraphRecursionError:
                # 死循环兜底：循环上限耗尽时不再把异常抛给用户（表现为"不返回结果"），
                # 尽量从 checkpointer 取回部分 state，用已收证据合成报告。
                try:
                    snapshot = await self.graph.aget_state(config)
                    return dict(snapshot.values or {}), True
                except Exception:
                    return {
                        "messages": [],
                        "research_question": question,
                        "user_input": question,
                    }, True

        final_state, recursion_hit = asyncio.run(_ainvoke_with_fallback())
        if recursion_hit:
            run_context.journal.append(
                "agent.recursion_limit",
                {"run_id": run_context.run_id, "question": question[:200]},
            )

        expert_mode = run_context.config.runtime.expert_mode
        artifact_path = None

        if expert_mode:
            # expert 模式：ReportMiddleware after_agent 已写 final_report 字段；用此 + 保存 artifact
            final_report = final_state.get("final_report") if isinstance(final_state, dict) else None
            if not final_report:
                # fallback：ReportMiddleware 未跑或 observations 空 → reporter 合成
                report_result = self.capability_registry.get_reporter().generate_report(final_state, run_context)
                final_report = report_result.final_report
            if run_context.config.reporting.save_artifact:
                artifact = self.capability_registry.get_artifact_store().save_artifact(
                    content=final_report,
                    output_dir=run_context.output_dir,
                    title="Final Report",
                    filename="final_report.md",
                    metadata={"mode": "expert"},
                )
                artifact_path = artifact.path
                run_context.journal.append(
                    "report.generated",
                    {
                        "artifact_id": artifact.artifact_id,
                        "title": artifact.title,
                        "path": artifact.path,
                        "mode": "expert",
                    },
                )
        else:
            # default 模式：不自动报告，输出 last AIMessage；不保存 artifact（靠 /report 触发）
            final_report = _last_ai_message(final_state) or ""
            if recursion_hit and not final_report:
                # 循环上限耗尽且模型没留下答案 → 用 observations 渲染结构化兜底
                try:
                    final_report = self.capability_registry.get_reporter().generate_report(
                        final_state, run_context,
                    ).final_report
                except Exception:
                    final_report = ""
                if not final_report:
                    final_report = f"# {question}\n\n研究因达到循环上限而中断，未收集到可用证据。"
            elif recursion_hit and "No answer collected." in final_report:
                final_report = f"# {question}\n\n研究因达到循环上限而中断，未收集到可用证据。"

        if recursion_hit:
            final_report = (
                f"{final_report}\n\n"
                "> 注意：本次运行达到循环上限被终止，以上内容基于已收集证据生成，可能不完整。"
                "可以缩小问题范围后重新提问。"
            )

        return AgentRunResult(
            run_id=run_context.run_id,
            thread_id=run_context.thread_id,
            final_report=final_report,
            events_path=str(run_context.events_path),
            artifact_path=artifact_path,
            state=final_state if isinstance(final_state, dict) else dict(final_state),
        )
