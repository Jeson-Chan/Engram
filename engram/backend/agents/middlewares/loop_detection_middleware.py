"""LoopDetectionMiddleware — ReAct 死循环 / 搜索过搜熔断器。

两层保护：

1. **同参重复**：最近 window 条消息里 (tool_name, args_hash) ≥ threshold → 熔断。
2. **单工具过搜**：搜索类工具（web_search 等）在同一个 run 内的调用次数
   达到 soft_limit → 注入"停止搜索、基于已有证据收尾"提醒；
   达到 hard_limit → 清掉最后一条 AIMessage 的 tool_calls + jump model 强制收尾；
   模型仍不收敛（连续 max_forced_finalizations 次）→ 注入确定性收尾
   AIMessage + jump end，保证 run 一定有结果。

背景（2026-11-20）：一次真实 run 连续调了 60 次 web_search，每次查询词都不同
（属于"越搜越细"的深挖型循环，第 1 层同参检测抓不到）；同时 ToolCallMiddleware
的总调用预算被放宽到 999，导致 run 迟迟不结束。第 2 层只约束搜索类工具，
不限制 bash 等长任务工具，阈值可用 LoopDetectionConfig 覆盖。

全模式挂（default + expert）。借鉴 deer-flow LoopDetectionMiddleware 思路。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from engram.backend.agents.middlewares.run_journal_middleware import _get_runtime_value
from engram.backend.agents.state.types import ThreadState

# 搜索类工具：只对这些工具做过搜熔断，避免误伤 bash/文件等长任务工具。
_SEARCH_TOOL_PREFIXES: tuple[str, ...] = ("web_search", "tavily", "deep_search", "search_")


@dataclass(frozen=True)
class LoopDetectionConfig:
    """LoopDetection 配置。"""

    enabled: bool = True
    window: int = 10  # 扫描最近 N 条消息
    threshold: int = 3  # 同 (tool, args) 出现 M 次触发
    # 单工具过搜熔断（解决"查询词每次不同"的深挖型循环）
    per_tool_soft_limit: int = 12  # 达到 → 注入停止提醒（只提醒一次）
    per_tool_hard_limit: int = 20  # 达到 → 强制收尾；超过 → 拒绝继续执行搜索
    max_forced_finalizations: int = 2  # 强制收尾尝试次数，超过则直接产出确定性答案


def _is_search_tool(tool_name: str) -> bool:
    """搜索类工具判定（skill_search 是本地技能检索，不计入过搜预算）。"""
    name = (tool_name or "").lower()
    if name == "skill_search":
        return False
    return name.startswith(_SEARCH_TOOL_PREFIXES)


def _hash_args(args: Any) -> str:
    """参数哈希。json sort_keys 截断 100 字，避免微小参数差异逃检测。"""
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False)[:100]
    except (TypeError, ValueError):
        return str(args)[:100]


def _detect_loop(
    messages: list[Any],
    window: int = 10,
    threshold: int = 3,
) -> str | None:
    """扫描最近 window 条消息，找重复 (tool_name, args_hash)。

    返回重复的 tool_name 或 None。
    """
    recent = messages[-window:] if window > 0 else messages
    call_counts: dict[tuple[str, str], int] = {}
    for msg in recent:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if not isinstance(tc, dict):
                    continue
                name = tc.get("name", "") or ""
                args = tc.get("args", {}) or {}
                key = (name, _hash_args(args))
                call_counts[key] = call_counts.get(key, 0) + 1
    for (name, _), count in call_counts.items():
        if count >= threshold:
            return name
    return None


def _build_guidance(loop_tool: str, detail: str = "") -> str:
    reason = detail or "重复调用循环"
    return (
        "<system_reminder>\n"
        f"检测到工具 {loop_tool} {reason}。"
        "请立即停止调用该工具，基于已有证据给出最终答案。"
        "如果信息仍有缺口，请在答案中明确说明缺口，不要再继续搜索。\n"
        "</system_reminder>"
    )


def _build_finalization_message(
    tool_name: str,
    call_count: int,
    sources: list[Any],
) -> str:
    """强制收尾的确定性答案（不能再依赖模型配合）。"""
    urls: list[str] = []
    for src in sources or []:
        url = src.get("url") if isinstance(src, dict) else getattr(src, "url", None)
        if url:
            urls.append(str(url))
    lines = [
        f"搜索工具 {tool_name} 已调用 {call_count} 次，达到循环保护上限，研究提前收尾。",
        "",
        "已收集到的来源：",
    ]
    if urls:
        lines.extend(f"- {u}" for u in urls[-10:])
    else:
        lines.append("- （本轮没有记录到可用来源）")
    lines.append("")
    lines.append("信息可能不完整。可以缩小问题范围后重新提问，或改用 expert 模式继续研究。")
    return "\n".join(lines)


class LoopDetectionMiddleware(AgentMiddleware):
    """ReAct 死循环 / 搜索过搜熔断器。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, config: LoopDetectionConfig | None = None) -> None:
        self._config = config or LoopDetectionConfig()
        self._lock = threading.Lock()
        # (thread_id, run_id, tool_name) -> 调用次数
        self._tool_counts: dict[tuple[str, str, str], int] = {}
        # (thread_id, run_id) -> 强制收尾次数
        self._forced: dict[tuple[str, str], int] = {}
        # (thread_id, run_id) -> 待注入的 before_model 提醒
        self._pending: dict[tuple[str, str], list[str]] = {}

    # ── run 级计数键 ────────────────────────────────────────────────

    def _run_key(self, runtime: Runtime) -> tuple[str, str]:
        tid = str(_get_runtime_value(runtime, "thread_id", None) or "default")
        rid = str(_get_runtime_value(runtime, "run_id", None) or "default")
        return (tid, rid)

    def _tool_key(self, runtime: Runtime, tool_name: str) -> tuple[str, str, str]:
        tid, rid = self._run_key(runtime)
        return (tid, rid, tool_name)

    def _saturated_tool(self, runtime: Runtime) -> tuple[str, int] | None:
        """当前 run 里达到 hard_limit 的搜索工具。"""
        tid, rid = self._run_key(runtime)
        with self._lock:
            self._prune_stale_runs(runtime)
            for (k_tid, k_rid, name), count in self._tool_counts.items():
                if (k_tid, k_rid) == (tid, rid) and count >= self._config.per_tool_hard_limit:
                    return name, count
        return None

    # ── 生命周期清理 ─────────────────────────────────────────────────

    @override
    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        """每次 graph invocation 视为一个新 run：清空该 thread 的计数。

        不能只按 run_id 区分——部分调用方（如 subagent 直调 LeaderAgent.invoke）
        不传 run_id，同 thread 多轮会累计到触发误熔断。
        """
        tid, _ = self._run_key(runtime)
        with self._lock:
            for key in list(self._tool_counts):
                if key[0] == tid:
                    self._tool_counts.pop(key, None)
            for key in list(self._forced):
                if key[0] == tid:
                    self._forced.pop(key, None)
            for key in list(self._pending):
                if key[0] == tid:
                    self._pending.pop(key, None)
        return None

    def _prune_stale_runs(self, runtime: Runtime) -> None:
        """清理同一 thread 下陈旧 run 的计数，防止跨轮累积误熔断。"""
        tid, rid = self._run_key(runtime)
        for key in list(self._tool_counts):
            if key[0] == tid and key[1] != rid:
                self._tool_counts.pop(key, None)
        for key in list(self._forced):
            if key[0] == tid and key[1] != rid:
                self._forced.pop(key, None)
        for key in list(self._pending):
            if key[0] == tid and key[1] != rid:
                self._pending.pop(key, None)

    # ── 工具调用计数 + 超限拒绝 ────────────────────────────────────

    def _count_and_check(self, request: ToolCallRequest) -> tuple[int, bool, bool]:
        """返回 (调用次数, 是否刚达 soft_limit, 是否已超过 hard_limit)。"""
        tool_name = request.tool_call.get("name", "") or ""
        key = self._tool_key(request.runtime, tool_name)
        with self._lock:
            self._prune_stale_runs(request.runtime)
            count = self._tool_counts.get(key, 0) + 1
            self._tool_counts[key] = count
            soft = count == self._config.per_tool_soft_limit
            saturated = count > self._config.per_tool_hard_limit
            if soft:
                run_key = self._run_key(request.runtime)
                self._pending.setdefault(run_key, []).append(
                    _build_guidance(
                        tool_name,
                        f"已调用 {count} 次，接近单次运行搜索上限",
                    )
                )
        return count, soft, saturated

    def _blocked_result(self, request: ToolCallRequest) -> Command:
        tool_name = request.tool_call.get("name", "") or ""
        count = self._config.per_tool_hard_limit
        return Command(update={"messages": [ToolMessage(
            content=(
                f"⚠️ 工具 {tool_name} 本次运行已调用 {count} 次，超过搜索上限，已被禁用。"
                "请立即基于已有证据输出最终答案。"
            ),
            tool_call_id=request.tool_call.get("id", ""),
            status="error",
        )]})

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "") or ""
        if not self._config.enabled or not _is_search_tool(tool_name):
            return handler(request)
        _, _, saturated = self._count_and_check(request)
        if saturated:
            return self._blocked_result(request)
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "") or ""
        if not self._config.enabled or not _is_search_tool(tool_name):
            return await handler(request)
        _, _, saturated = self._count_and_check(request)
        if saturated:
            return self._blocked_result(request)
        return await handler(request)

    # ── 提醒注入 ────────────────────────────────────────────────────

    @hook_config(can_jump_to=["model"])
    @override
    def before_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        key = self._run_key(runtime)
        with self._lock:
            pending = self._pending.pop(key, None) or []
        if not pending:
            return None
        return {"messages": [HumanMessage(
            name="loop_detection",
            additional_kwargs={"hide_from_ui": True},
            content="\n\n".join(dict.fromkeys(pending)),
        )]}

    @hook_config(can_jump_to=["model"])
    @override
    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    # ── 熔断 ────────────────────────────────────────────────────────

    @hook_config(can_jump_to=["model", "end"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        if not self._config.enabled:
            return None
        messages = state.get("messages") or []
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not getattr(last_ai, "tool_calls", None):
            # 模型本轮想退出：不熔断（即使历史里有重复/过搜）
            return None

        loop_tool = _detect_loop(messages, self._config.window, self._config.threshold)
        saturated = self._saturated_tool(runtime)
        if loop_tool is None and saturated is None:
            return None

        if saturated is not None:
            tool_name, count = saturated
            run_key = self._run_key(runtime)
            with self._lock:
                forced = self._forced.get(run_key, 0) + 1
                self._forced[run_key] = forced
            if forced > self._config.max_forced_finalizations:
                # 模型连续拒绝收尾 → 注入确定性答案并结束，保证 run 有结果。
                return {
                    "messages": [AIMessage(content=_build_finalization_message(
                        tool_name, count, state.get("sources") or [],
                    ))],
                    "jump_to": "end",
                }
            guidance_text = _build_guidance(
                tool_name,
                f"已达到单次运行搜索上限（{count} 次）",
            )
        else:
            tool_name = loop_tool or ""
            guidance_text = _build_guidance(tool_name)

        # 清 tool_calls 强制模型给最终答案，保留 content + 标记 loop_detected。
        # 复用原 id → add_messages 按 id 替换原消息（非追加），否则原 AIMessage 的
        # tool_calls 仍留 history，jump_to model 跳过 ToolNode 后无 ToolMessage 配对 →
        # 下一轮 model 调用 400: insufficient tool messages following tool_calls。
        # 同步剥 additional_kwargs.tool_calls/function_call 防 _has_tool_call_intent 误判。
        new_kwargs = {
            k: v for k, v in (last_ai.additional_kwargs or {}).items()
            if k not in ("tool_calls", "function_call")
        }
        new_kwargs["loop_detected"] = tool_name
        cleared = AIMessage(
            id=last_ai.id,
            content=last_ai.content or "",
            tool_calls=[],
            additional_kwargs=new_kwargs,
        )
        guidance = HumanMessage(
            name="loop_detection",
            additional_kwargs={"hide_from_ui": True},
            content=guidance_text,
        )
        return {"messages": [cleared, guidance], "jump_to": "model"}

    @hook_config(can_jump_to=["model", "end"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)