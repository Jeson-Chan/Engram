"""客户端视图模型 — Web/TUI 共用的只读序列化层。

设计依据（OpenSpec change web-tui-research-workbench，design.md 决策 3）：
内部 dataclass（SessionRecord / MemoryTrace / RunEvent / BaseMessage）不直接
暴露给前端；本模块把它们归一化为稳定契约：

- SessionSummary：会话摘要（列表/详情）
- MessageView：历史消息（回放对话界面）
- MemoryTraceView：记忆条目（Memory Explorer）
- RunEventView：Run 时间线事件
- RuntimeStatus：客户端状态（模型/能力可用性）

INVARIANT:
- 时间字段一律 ISO-8601 字符串（缺失时 None，不猜测）
- 枚举一律取 value 字符串（"episodic"/"semantic"/"procedural"），不传枚举对象
- 所有模型可 model_dump() 直接 JSON 序列化
- 不含密钥/内部存储键格式
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import BaseModel, Field

from engram.backend.agents.journal.events import RunEvent
from engram.backend.agents.memory.schema import MemoryTrace


def _iso_or_none(value: Any) -> str | None:
    """时间值 → ISO 字符串；None/非数值返回 None（不猜测）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    return None


class SessionSummary(BaseModel):
    """会话摘要（Web 会话栏 / TUI 会话列表共用）。"""

    session_id: str
    thread_id: str
    title: str
    user_id: str
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int = 0
    memory_count: int = 0
    last_run_status: str | None = None


class MessageView(BaseModel):
    """历史消息（checkpointer 回放；顺序由调用方保证）。"""

    role: str
    content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    msg_id: str | None = None
    created_at: str | None = None


class MemoryTraceView(BaseModel):
    """记忆条目（Memory Explorer / 召回提示展开共用）。"""

    id: str
    content: str
    type: str
    strength: float
    decay_rate: float
    access_count: int
    source: str | None = None
    created_at: str | None = None
    forgotten: bool = False
    layer: str | None = None  # "hot" | "cold" | None（未知）


class RunEventView(BaseModel):
    """Run 时间线事件（Inspector）。"""

    event_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class RuntimeStatus(BaseModel):
    """客户端状态：模型/模式与已加载能力；绝不含密钥。"""

    model: str | None = None
    provider: str | None = None
    mode: str | None = None  # "expert" | "lightweight"
    deployment: str | None = None  # "docker" | "venv"（后端启动方式；绝不含密钥）
    skills: list[dict[str, Any]] = Field(default_factory=list)
    mcp: list[dict[str, Any]] = Field(default_factory=list)
    sandbox: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 序列化函数（内部对象 → 视图模型）
# ---------------------------------------------------------------------------


def session_summary_from(
    record: Any,
    *,
    title: str | None = None,
    updated_at: Any = None,
    message_count: int = 0,
    memory_count: int = 0,
    last_run_status: str | None = None,
) -> SessionSummary:
    """SessionRecord（或鸭子类型同构对象）→ SessionSummary。

    title 缺省取 metadata.title 或 "Session {session_id 前 8 位}"。
    """
    metadata: dict = getattr(record, "metadata", None) or {}
    sid = str(getattr(record, "session_id", ""))
    return SessionSummary(
        session_id=sid,
        thread_id=str(getattr(record, "thread_id", "")),
        title=title or str(metadata.get("title") or f"Session {sid[:8]}"),
        user_id=str(getattr(record, "user_id", "default-user")),
        created_at=_iso_or_none(getattr(record, "created_at", None)),
        updated_at=_iso_or_none(updated_at),
        message_count=message_count,
        memory_count=memory_count,
        last_run_status=last_run_status,
    )


def message_view_from(msg: BaseMessage) -> MessageView:
    """LangChain message → MessageView（role 取小写类名前缀）。"""
    role = msg.__class__.__name__.lower().removesuffix("chunk").removesuffix("message")
    if isinstance(msg, ToolMessage):
        role = "tool"
    tool_calls: list[dict[str, Any]] = []
    if isinstance(msg, AIMessage):
        for tc in msg.tool_calls or []:
            tool_calls.append({
                "name": str(tc.get("name", "")),
                "args": tc.get("args") or {},
                "id": tc.get("id"),
            })
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    response_meta = getattr(msg, "response_metadata", None) or {}
    return MessageView(
        role=role,
        content=content,
        tool_calls=tool_calls,
        msg_id=getattr(msg, "id", None),
        created_at=_iso_or_none(response_meta.get("created_at")),
    )


def memory_trace_view_from(trace: MemoryTrace, layer: str | None = None) -> MemoryTraceView:
    """MemoryTrace → MemoryTraceView；forgotten 读 metadata（遗忘策略标记）。"""
    metadata: dict = getattr(trace, "metadata", None) or {}
    return MemoryTraceView(
        id=trace.id,
        content=trace.content,
        type=trace.type.value if hasattr(trace.type, "value") else str(trace.type),
        strength=round(float(trace.strength), 4),
        decay_rate=round(float(trace.decay_rate), 4),
        access_count=int(trace.access_count),
        source=trace.source,
        created_at=_iso_or_none(trace.created_at),
        forgotten=bool(metadata.get("forgotten", False)),
        layer=layer,
    )


def run_event_view_from(event: RunEvent) -> RunEventView:
    """RunEvent → RunEventView。"""
    return RunEventView(
        event_id=event.event_id,
        event_type=event.event_type,
        payload=dict(event.payload),
        created_at=_iso_or_none(event.created_at),
    )


def runtime_status_from_runtime(runtime: Any) -> RuntimeStatus:
    """AppRuntime → RuntimeStatus（防御式读取；能力未装配时给空态）。

    provider 在模型路由层解析，此处 best-effort（env ENGRAM_PROVIDER 或 None），
    /status 端点可在装配时补齐。
    """
    import os

    config = getattr(runtime, "config", None)
    runtime_cfg = getattr(config, "runtime", None) if config is not None else None

    mode: str | None = None
    if runtime_cfg is not None and hasattr(runtime_cfg, "expert_mode"):
        mode = "expert" if runtime_cfg.expert_mode else "lightweight"

    skills: list[dict[str, Any]] = []
    skill_manager = getattr(runtime, "skill_manager", None)
    if skill_manager is not None and hasattr(skill_manager, "list_skills"):
        try:
            skills = list(skill_manager.list_skills())
        except Exception:
            skills = []

    mcp: list[dict[str, Any]] = []
    mcp_manager = getattr(runtime, "mcp_manager", None)
    if mcp_manager is not None and hasattr(mcp_manager, "list_servers"):
        try:
            mcp = list(mcp_manager.list_servers())
        except Exception:
            mcp = []

    sandbox: dict[str, Any] = {}
    sandbox_cfg = getattr(config, "sandbox", None) if config is not None else None
    if sandbox_cfg is not None:
        sandbox = {
            "use": getattr(sandbox_cfg, "use", None),
            "timeout": getattr(sandbox_cfg, "timeout", None),
        }

    from engram.backend.app.cli.probes import probe_deployment

    deployment_probe = probe_deployment()

    return RuntimeStatus(
        model=getattr(runtime, "researcher_model_name", None),
        provider=os.environ.get("ENGRAM_PROVIDER") or None,
        mode=mode,
        deployment="docker" if deployment_probe.available else "venv",
        skills=skills,
        mcp=mcp,
        sandbox=sandbox,
    )
