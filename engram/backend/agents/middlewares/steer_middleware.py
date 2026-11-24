"""SteerMiddleware — 运行中插话注入（real-steer）。

before_model 排空当前 thread 的 steer 队列，把插话作为 HumanMessage 追加进
对话状态——模型在下一步即看到用户补充。journal 记 ``steer.injected``；
经 get_stream_writer 发 ``steer_injected`` 事件（TUI/web 显示"已注入"）。
after_agent 清空残留（run 结束后到达的插话属陈旧，防误注入下一 run）。

INVARIANT:
- 队列空 → 返回 None（零开销）
- 注入即消费（drain），同一条不重复
- journal / 流事件失败静默（不阻塞注入）
"""
from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from engram.backend.agents.middlewares.run_journal_middleware import _get_runtime_value
from engram.backend.agents.middlewares.steer_queue import SteerQueues


class SteerMiddleware(AgentMiddleware):
    """before_model 注入插话；after_agent 清残留。"""

    def __init__(self, queues: SteerQueues) -> None:
        self._queues = queues

    def _thread_id(self, runtime: Runtime) -> str | None:
        return _get_runtime_value(runtime, "thread_id")

    @override
    def before_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        thread_id = self._thread_id(runtime)
        if not thread_id:
            return None
        texts = self._queues.drain(thread_id)
        if not texts:
            return None

        journal = _get_runtime_value(runtime, "journal", None)
        run_id = _get_runtime_value(runtime, "run_id", None)
        for text in texts:
            if journal is not None:
                try:
                    journal.append("steer.injected", {
                        "text": text, "run_id": run_id, "thread_id": thread_id,
                    })
                except Exception:
                    pass
            try:
                from langgraph.config import get_stream_writer

                get_stream_writer()({"type": "steer_injected", "content": text})
            except Exception:
                pass
        return {"messages": [HumanMessage(content=t) for t in texts]}

    @override
    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    @override
    def after_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        thread_id = self._thread_id(runtime)
        if thread_id:
            self._queues.clear(thread_id)
        return None

    @override
    async def aafter_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)