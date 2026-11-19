"""记忆查询只读端点 — GET /memory/stats、GET /memory/traces，
记忆清除端点 — DELETE /memory/traces（memory-management-ui）。

gateway-client-api / 记忆查询（design.md 决策 6）：只读包装
TieredMemoryStore（layer_of/iter_views），不新建记忆后端。

- 过滤：user / 文本 / 类型 / 强度 / 遗忘 / 层
- 每条结果：MemoryTraceView（含 hot/cold 层与 forgotten 标记）
- stats：hot / cold / forgotten / consolidation 数量
- 记忆未启用（ENGRAM_MEMORY_USE 为空）→ 503 明确提示
- 跨用户：user_id 过滤按 trace metadata 归属（无 metadata 视为 default）

DELETE /memory/traces（清除能力，spec specs/memory-clearance）：
- 三档粒度：trace_id（单条）/ user_id+thread_id（thread）/ user_id（user）
- preview=true 只返回将删计数（与删除同一套定位谓词，design.md 决策 4）
- 硬删除：hot+cold 同删，不可逆；删除事件写 journal 留痕（不含正文）
- 不提供"全部清空"粒度（spec MUST NOT）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from engram.backend.app.gateway.views import MemoryTraceView, memory_trace_view_from

logger = logging.getLogger(__name__)


def _memory_store(app) -> Any:
    """runtime → memory provider → store；未启用/runtime 缺 → None。"""
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return None
    registry = getattr(runtime, "capability_registry", None)
    provider = getattr(registry, "memory_provider", None)
    if provider is None:
        return None
    try:
        return provider.store()
    except Exception:
        return None


def _memory_provider(app) -> Any:
    """runtime → capability_registry → memory provider；缺 → None。"""
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return None
    registry = getattr(runtime, "capability_registry", None)
    return getattr(registry, "memory_provider", None)


def _emit_memory_journal(app, event: str, payload: dict) -> None:
    """删除留痕：经 provider.manager 的 journal 回调发事件（不含记忆正文）。

    journal 回调不可用（记忆侧 journal 未注入）时降级为结构化日志，
    不阻断删除主流程。
    """
    provider = _memory_provider(app)
    manager_factory = getattr(provider, "manager", None)
    emit = None
    if callable(manager_factory):
        try:
            emit = getattr(manager_factory(), "_emit_journal", None)
        except Exception:
            emit = None
    if callable(emit):
        try:
            emit(event, payload)
            return
        except Exception:
            logger.warning("memory journal emit failed for %s", event, exc_info=True)
    logger.info("memory %s %s", event, payload)


def _thread_of(trace: Any) -> str:
    """trace 的归属 thread（与各 store _partition_of 同语义）。"""
    metadata = getattr(trace, "metadata", None) or {}
    thread_id = metadata.get("thread_id")
    if thread_id:
        return str(thread_id)
    source = getattr(trace, "source", None) or ""
    if source.startswith("worker:"):
        return source.split(":")[1]
    return "default"


def _partition_ids_of(store: Any, user_id: str, thread_id: str | None) -> list[str]:
    """分区定位（预览/删除同一谓词，design.md 决策 4）。

    store 有 list_partition 原语则直接用（与 remove_partition 同谓词）；
    否则按与 store _partition_of 同语义的谓词过滤全量视图。
    """
    lister = getattr(store, "list_partition", None)
    if callable(lister):
        try:
            return list(lister(user_id, thread_id))
        except Exception:
            pass
    out: list[str] = []
    for trace, _layer in _all_views(store):
        if _user_of(trace) != user_id:
            continue
        if thread_id is not None and _thread_of(trace) != thread_id:
            continue
        out.append(trace.id)
    return out


def _exists(store: Any, trace_id: str) -> bool:
    """无副作用存在探测：layer_of（hot/cold 标注）优先，回退 get。"""
    layer_of = getattr(store, "layer_of", None)
    if callable(layer_of):
        try:
            return layer_of(trace_id) is not None
        except Exception:
            return False
    try:
        return store.get(trace_id) is not None
    except Exception:
        return False


def _layer_of(store: Any, trace_id: str) -> str | None:
    """层标注：TieredMemoryStore 有 layer_of 则用之，否则 None。"""
    layer_of = getattr(store, "layer_of", None)
    if callable(layer_of):
        try:
            return layer_of(trace_id)
        except Exception:
            return None
    return None


def _view_of(store: Any, trace: Any, layer: str | None = None) -> MemoryTraceView:
    """层标注优先用已算好的 layer（_all_views 一趟带出——review performance：
    每条单独 layer_of 是 2 次远程 GET，且 Redis get 会续命热层）。"""
    if layer is None:
        layer = _layer_of(store, trace.id)
    return memory_trace_view_from(trace, layer=layer)


def _user_of(trace: Any) -> str:
    """trace 的归属用户。

    review medium：sentinel 必须与网关默认会话用户一致（"default-user"，
    SessionCreateRequest/registry 同款）——此前用 "default"，
    默认用户的查询会把旧 trace 全部过滤掉。
    """
    metadata = getattr(trace, "metadata", None) or {}
    return str(metadata.get("user_id") or "default-user")


def _matches(
    trace: Any,
    *,
    user_id: str | None,
    q: str | None,
    type_filter: str | None,
    min_strength: float,
    forgotten: bool | None,
) -> bool:
    if user_id is not None and _user_of(trace) != user_id:
        return False
    if q:
        content = getattr(trace, "content", "") or ""
        if q.lower() not in content.lower():
            return False
    if type_filter is not None:
        t = getattr(trace, "type", None)
        t_value = getattr(t, "value", str(t))
        if t_value != type_filter:
            return False
    if float(getattr(trace, "strength", 0.0)) < min_strength:
        return False
    metadata = getattr(trace, "metadata", None) or {}
    is_forgotten = bool(metadata.get("forgotten", False))
    if forgotten is not None and is_forgotten != forgotten:
        return False
    return True


def mount_memory_routes(app: FastAPI) -> None:
    """记忆查询端点挂载（main.create_app 内调用）。"""

    @app.get("/memory/stats")
    def memory_stats(user_id: str | None = Query(default=None)) -> dict:
        store = _memory_store(app)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="memory not configured (set ENGRAM_MEMORY_USE and Redis/PG)",
            )
        stats = {"hot": 0, "cold": 0, "forgotten": 0, "consolidation": 0, "total": 0}
        for trace, layer in _all_views(store):
            if user_id is not None and _user_of(trace) != user_id:
                continue
            stats["total"] += 1
            if layer == "hot":
                stats["hot"] += 1
            elif layer == "cold":
                stats["cold"] += 1
            metadata = getattr(trace, "metadata", None) or {}
            if metadata.get("forgotten"):
                stats["forgotten"] += 1
            if metadata.get("consolidated_from") is not None:
                stats["consolidation"] += 1
        return stats

    @app.get("/memory/traces", response_model=list[MemoryTraceView])
    def memory_traces(
        user_id: str | None = Query(default=None),
        q: str | None = Query(default=None),
        type: str | None = Query(default=None),
        min_strength: float = Query(default=0.0, ge=0.0, le=1.0),
        forgotten: bool | None = Query(default=None),
        layer: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[MemoryTraceView]:
        store = _memory_store(app)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="memory not configured (set ENGRAM_MEMORY_USE and Redis/PG)",
            )
        out: list[MemoryTraceView] = []
        for trace, trace_layer in _all_views(store):
            if not _matches(
                trace, user_id=user_id, q=q, type_filter=type,
                min_strength=min_strength, forgotten=forgotten,
            ):
                continue
            if layer is not None and (trace_layer or "") != layer:
                continue
            out.append(_view_of(store, trace, trace_layer))
            if len(out) >= limit:
                break
        return out

    @app.delete("/memory/traces")
    def delete_memory_traces(
        trace_id: str | None = Query(default=None),
        user_id: str | None = Query(default=None),
        thread_id: str | None = Query(default=None),
        preview: bool = Query(default=False),
    ) -> dict:
        """记忆清除（硬删除，spec specs/memory-clearance）。

        - trace_id：单条；user_id+thread_id：thread 粒度；user_id：user 粒度
        - preview=true：只返回将删计数，不调用删除原语
        - 不提供"全部清空"粒度（user_id 缺省时不构成任何删除操作）
        """
        store = _memory_store(app)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="memory not configured (set ENGRAM_MEMORY_USE and Redis/PG)",
            )

        # ---- 单条粒度 ----
        if trace_id is not None:
            if user_id is not None or thread_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="trace_id granularity is single-trace;"
                           " do not combine with user_id/thread_id",
                )
            if preview:
                count = 1 if _exists(store, trace_id) else 0
                return {"grain": "trace", "preview": True,
                        "count": count, "trace_id": trace_id}
            if not _exists(store, trace_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"memory trace not found: {trace_id}",
                )
            store.remove(trace_id)
            _emit_memory_journal(app, "memory.remove.trace", {
                "grain": "trace", "trace_id": trace_id, "deleted": 1,
            })
            return {"grain": "trace", "preview": False,
                    "deleted": 1, "trace_id": trace_id}

        # ---- thread / user 粒度 ----
        if user_id is None:
            raise HTTPException(
                status_code=400,
                detail="specify trace_id (single), or user_id"
                       " (optionally with thread_id) for partition clearance",
            )
        grain = "thread" if thread_id is not None else "user"
        ids = _partition_ids_of(store, user_id, thread_id)
        if preview:
            return {"grain": grain, "preview": True, "count": len(ids),
                    "trace_ids": ids[:500],
                    "user_id": user_id, "thread_id": thread_id}

        remover = getattr(store, "remove_partition", None)
        if callable(remover):
            removed = list(remover(user_id, thread_id))
        else:
            # store 无分区原语：按同一谓词逐条 remove（最终一致）
            removed = []
            for tid in ids:
                try:
                    store.remove(tid)
                    removed.append(tid)
                except Exception:
                    logger.warning("partition remove failed for %s", tid,
                                   exc_info=True)
        _emit_memory_journal(app, "memory.remove.partition", {
            "grain": grain, "user_id": user_id,
            "thread_id": thread_id, "deleted": len(removed),
        })
        return {"grain": grain, "preview": False, "deleted": len(removed),
                "trace_ids": removed[:500],
                "user_id": user_id, "thread_id": thread_id}


def _all_views(store: Any) -> list[tuple[Any, str | None]]:
    """全量 (trace, layer) 视图——iter_views 一趟带层；否则 list_all + 逐条标注。"""
    iter_views = getattr(store, "iter_views", None)
    if callable(iter_views):
        try:
            return list(iter_views())
        except Exception:
            pass
    try:
        return [(trace, _layer_of(store, trace.id)) for trace in store.list_all()]
    except Exception:
        return []
