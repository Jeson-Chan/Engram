"""ReflectionMiddleware — ReAct 退出闸门，简单反思（L1 充分性）。

after_model：模型想退出时，用 observations 对 todos step 覆盖度判断实质充分性。
不足 → reflection_items + jump_to model 补研究。外壳 + 可替换 Strategy 架构，
ReflectionAction 契约预留 revise_plan/backtrack/rollback_to 供未来 L2/L3 扩展。
仅 general/expert 启用。完整设计见 design_docs/15-reflection-middleware-design.md。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Protocol, TypedDict, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from engram.backend.agents.middlewares import _jump_budget
from engram.backend.agents.middlewares.run_journal_middleware import _get_runtime_value
from engram.backend.agents.middlewares.todo_middleware import _has_persistent_failures, _has_tool_call_intent
from engram.backend.agents.prompts import get_prompt_manager
from engram.backend.agents.state.types import ReflectionItem, ThreadState


class ReflectionAction(TypedDict):
    """策略返回的动作契约。L1 只用 pass/continue；revise_plan/backtrack/rollback_to 预留。"""

    verdict: str  # "pass" | "continue" | "revise_plan" | "backtrack"
    reflection_items: list[Any]
    plan: Any  # revise_plan/backtrack 时的新 plan，否则 None
    guidance: str  # 注回模型的提示
    rollback_to: str  # backtrack 回退到的决策节点 id（L3 未来）


class ReflectionStrategy(Protocol):
    def reflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction: ...


def _make_reflection_id() -> str:
    return f"refl-{uuid.uuid4().hex[:12]}"


def _step_id(obs: Any) -> str | None:
    if isinstance(obs, dict):
        return obs.get("step_id")
    return getattr(obs, "step_id", None)


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _internal_timeout() -> float:
    """内部 LLM 调用超时（reflection / summarizer）。防止 provider 卡住时挂死整个 run。"""
    try:
        return float(os.environ.get("ENGRAM_INTERNAL_LLM_TIMEOUT", "60"))
    except (TypeError, ValueError):
        return 60.0


def _pass_action() -> ReflectionAction:
    return ReflectionAction(verdict="pass", reflection_items=[], plan=None, guidance="", rollback_to="")


def _continue_action(question: str, guidance: str) -> ReflectionAction:
    item = ReflectionItem(
        item_id=_make_reflection_id(), scope="run", kind="gap",
        question=question,
        related_refs=(),
    )
    return ReflectionAction(verdict="continue", reflection_items=[item], plan=None, guidance=guidance, rollback_to="")


def _is_sufficient(content: str) -> bool:
    """容错解析充分性 JSON；解析失败按"不充分"处理（回退规则逻辑）。"""
    import json

    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        return False
    try:
        return bool(json.loads(content[start:end]).get("sufficient", True))
    except Exception:
        return False


_CONTINUE_GUIDANCE = (
    "<system_reminder>\n"
    "LLM 评估认为当前证据不足以充分支撑研究结论，请补充搜索/调研后再给出最终答案。\n"
    "</system_reminder>"
)


class LightReflectionStrategy:
    """default 模式轻量策略：不 jump，直接 pass。

    default 模式不强制补研究——模型给答案即结束。保留 ReflectionMiddleware 外壳
    （触发时机 + jump 预算管理），但判断逻辑恒 pass。
    """

    def reflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction:
        return _pass_action()

    async def areflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction:
        return _pass_action()


class SufficiencyStrategy:
    """L1 充分性守门：todos 全完成时，检查每步是否有 observation 覆盖。

    F7：覆盖度判断交 LLM 评估（若提供 model），否则保持"每步有无 observation"判断（MVP 过渡）。
    未完成 todo 交给 Todo Layer 2，Reflection 只在 todo 全完成时判实质充分。
    非研究类问题（personal）直接 pass + 提示，避免 reflection 死循环。

    注意：async 图必须走 areflect（ainvoke + 超时）。旧实现 aafter_model 直接调同步
    llm.invoke，会阻塞 Textual 事件循环（2026-11-21 TUI ESC 后无响应故障）。
    """

    _RESEARCH_KEYWORDS = frozenset({
        "调研", "分析", "对比", "搜索", "报告", "研究", "深度", "了解",
        "收集", "整理", "调查", "评估", "综述", "总结", "查找", "查询",
        "research", "analyze", "compare", "search", "report", "study",
        "investigate", "survey", "review", "summary", "find", "deep dive",
    })

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def _classify_question(self, state: dict[str, Any]) -> str:
        """分类问题类型：research / personal / mixed。"""
        question = (state.get("research_question") or state.get("user_input") or "").lower()
        has_research_kw = any(kw in question for kw in self._RESEARCH_KEYWORDS)
        has_observations = bool(state.get("observations"))
        has_todos = bool(state.get("todos"))
        if has_todos or has_observations:
            return "research" if has_research_kw else "mixed"
        return "research" if has_research_kw else "personal"

    def _precheck(self, state: dict[str, Any]) -> ReflectionAction | None:
        """无需 LLM 的短路判断；返回 None 表示需要继续（可能调 LLM）。"""
        # 非研究类问题直接 pass + 提示，避免 reflection 死循环
        if self._classify_question(state) == "personal":
            return ReflectionAction(
                verdict="pass", reflection_items=[], plan=None,
                guidance=(
                    "<system_reminder>\n"
                    "该问题似乎不需要深度研究。建议 /default 模式对话，"
                    "或提供更具体的研究方向。当前将直接回答。\n"
                    "</system_reminder>"
                ),
                rollback_to="",
            )

        todos = state.get("todos") or []
        if todos and not all(t.get("status") == "completed" for t in todos):
            return _pass_action()

        # F8.4：失败超阈放宽
        if _has_persistent_failures(state):
            return _pass_action()

        if not (state.get("observations") or []):
            return _pass_action()

        return None

    def reflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction:
        early = self._precheck(state)
        if early is not None:
            return early
        todos = state.get("todos") or []
        observations = state.get("observations") or []
        # F7：有 LLM 则交模型评估充分性；否则保持每步覆盖度判断（MVP 过渡）
        if self._llm is not None:
            return self._llm_evaluate(state, todos, observations)
        return self._rule_based_check(todos, observations)

    async def areflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction:
        early = self._precheck(state)
        if early is not None:
            return early
        todos = state.get("todos") or []
        observations = state.get("observations") or []
        if self._llm is not None:
            return await self._allm_evaluate(state, todos, observations)
        return self._rule_based_check(todos, observations)

    def _rule_based_check(self, todos: list, observations: list) -> ReflectionAction:
        """MVP 过渡：每步有无 observation 覆盖度判断。"""
        covered = {_step_id(o) for o in observations if _step_id(o)}
        missing = [f"todo-{i}" for i, _ in enumerate(todos) if f"todo-{i}" not in covered]
        if not missing:
            return _pass_action()
        item = ReflectionItem(
            item_id=_make_reflection_id(), scope="run", kind="gap",
            question=f"以下步骤标记完成但缺少证据覆盖：{', '.join(missing)}",
            related_refs=tuple(missing),
        )
        guidance = (
            "<system_reminder>\n"
            f"以下研究步骤已标记完成但缺少证据支撑：{', '.join(missing)}。\n"
            "请针对这些步骤补充搜索/调研，确保每步都有 observations 证据后再给出最终答案。\n"
            "</system_reminder>"
        )
        return ReflectionAction(verdict="continue", reflection_items=[item], plan=None, guidance=guidance, rollback_to="")

    def _eval_prompt(self, state: dict[str, Any], todos: list, observations: list) -> str:
        question = state.get("research_question") or state.get("user_input") or ""
        todos_desc = "\n".join(f"- {t.get('content', '')}" for t in todos) if todos else "（无 todo）"
        obs_desc = "\n".join(
            f"- [{_step_id(o) or '-'}] {(_field(o, 'content') or '')[:200]}"
            for o in observations[:10]
        )
        return get_prompt_manager().load(
            "reflection", "sufficiency",
            question=question, todos_desc=todos_desc, obs_desc=obs_desc,
        )

    def _llm_evaluate(self, state: dict[str, Any], todos: list, observations: list) -> ReflectionAction:
        """同步路径（CLI 的 sync graph）；async 图请走 _allm_evaluate。"""
        prompt = self._eval_prompt(state, todos, observations)
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)], config={"tags": ["internal_llm"]})
            if _is_sufficient(getattr(resp, "content", str(resp))):
                return _pass_action()
        except Exception:
            pass  # LLM 评估失败则回退规则判断
        return _continue_action("LLM 评估证据不足以支撑研究结论", _CONTINUE_GUIDANCE)

    async def _allm_evaluate(self, state: dict[str, Any], todos: list, observations: list) -> ReflectionAction:
        """异步路径：ainvoke + 超时，不阻塞事件循环（TUI/gateway）。"""
        prompt = self._eval_prompt(state, todos, observations)
        try:
            resp = await asyncio.wait_for(
                self._llm.ainvoke([HumanMessage(content=prompt)], config={"tags": ["internal_llm"]}),
                timeout=_internal_timeout(),
            )
            if _is_sufficient(getattr(resp, "content", str(resp))):
                return _pass_action()
        except Exception:
            pass
        return _continue_action("LLM 评估证据不足以支撑研究结论", _CONTINUE_GUIDANCE)


class ReflectionMiddleware(AgentMiddleware):
    """外壳：管触发时机 + jump 预算；判断逻辑委托给 ReflectionStrategy。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, strategy: ReflectionStrategy | None = None, llm: Any = None) -> None:
        self._strategy = strategy or SufficiencyStrategy(llm=llm)

    @staticmethod
    def _emit(runtime: Runtime, event_type: str, payload: dict[str, Any]) -> None:
        """F3: 发 reflection 事件到 journal（经 _get_runtime_value 取 journal）。"""
        journal = _get_runtime_value(runtime, "journal", None)
        if journal is not None:
            journal.append(event_type, payload)

    def _should_gate(self, state: ThreadState) -> bool:
        messages = state.get("messages") or []
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        return bool(last_ai and not _has_tool_call_intent(last_ai))

    def _apply_action(
        self, action: ReflectionAction, runtime: Runtime,
    ) -> dict[str, Any] | None:
        if action["verdict"] == "pass":
            return None

        # F3: 共享 jump 预算门（与 Todo 合计 ≤3）；预算耗尽放行时发事件。
        if not _jump_budget.try_consume(runtime):
            self._emit(runtime, "reflection.budget_exhausted", {"max": _jump_budget._MAX_TOTAL_JUMPS})
            return None

        # F3: 触发 jump 时发 reflection.fired 事件。
        gap_steps = [getattr(it, "related_refs", ()) for it in action["reflection_items"]]
        self._emit(runtime, "reflection.fired", {
            "verdict": action["verdict"],
            "gap_steps": gap_steps,
            "remaining_budget": _jump_budget.remaining(runtime),
        })

        update: dict[str, Any] = {"reflection_items": action["reflection_items"]}
        if action["guidance"]:
            update["messages"] = [HumanMessage(
                name="reflection",
                additional_kwargs={"hide_from_ui": True},
                content=action["guidance"],
            )]
        if action["plan"]:
            update["plan"] = action["plan"]
        return {"jump_to": "model", **update}

    @hook_config(can_jump_to=["model"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        if not self._should_gate(state):
            return None
        action = self._strategy.reflect(state if isinstance(state, dict) else dict(state), runtime)
        return self._apply_action(action, runtime)

    @hook_config(can_jump_to=["model"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        if not self._should_gate(state):
            return None
        state_dict = state if isinstance(state, dict) else dict(state)
        areflect = getattr(self._strategy, "areflect", None)
        if callable(areflect):
            action = await areflect(state_dict, runtime)
        else:
            # 自定义策略只有同步实现：丢线程池，不阻塞 TUI/gateway 事件循环。
            action = await asyncio.to_thread(self._strategy.reflect, state_dict, runtime)
        return self._apply_action(action, runtime)
