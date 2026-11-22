"""Run 事件时间线 + 客户端状态端点 — GET /runs/{id}/events、GET /status。

gateway-client-api / 运行事件与状态（design.md 决策 7）：
- 事件来自持久运行日志（RunJournal JSONL，磁盘），不是内存
- 终态来自运行记录（PGRunStore 优先，进程内 RunManager 兜底）
- 状态 = RuntimeStatus（模型/模式/Skill/MCP/Sandbox 可用情况，无密钥）

路径解析（run_id → events.jsonl）：
- 网关 run：`<logs_root>/<run_id>/events.jsonl`（create_run 未传 thread_dir）
- CLI/带 thread_dir 的 run：`<logs_root>/threads/<thread_id>/runs/<run_id>/events.jsonl`
  （thread_id 从运行记录取）

404：run 无记录也无日志；503：runtime 未就绪。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from engram.backend.app.gateway.views import (
    RunEventView,
    RuntimeStatus,
    run_event_view_from,
    runtime_status_from_runtime,
)

logger = logging.getLogger(__name__)


def _logs_root(app) -> Path | None:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return None
    config = getattr(runtime, "config", None)
    runtime_cfg = getattr(config, "runtime", None) if config is not None else None
    logs_root = getattr(runtime_cfg, "logs_root", None) if runtime_cfg is not None else None
    return Path(str(logs_root)) if logs_root else None


def _thread_id_of_run(app, run_id: str) -> str | None:
    """运行记录的 thread_id：PGRunStore 优先，进程内 RunManager 兜底。"""
    store = getattr(app.state, "run_store", None)
    if store is not None:
        try:
            record = store.get_run(run_id)
            if record is not None:
                return record.get("thread_id")
        except Exception:
            pass
    runtime = getattr(app.state, "runtime", None)
    if runtime is not None:
        rec = runtime.run_manager.get_run(run_id)
        if rec is not None:
            return rec.thread_id
    return None


def _status_of_run(app, run_id: str) -> str | None:
    store = getattr(app.state, "run_store", None)
    if store is not None:
        try:
            record = store.get_run(run_id)
            if record is not None:
                return record.get("status")
        except Exception:
            pass
    runtime = getattr(app.state, "runtime", None)
    if runtime is not None:
        rec = runtime.run_manager.get_run(run_id)
        if rec is not None:
            status = getattr(rec, "status", None)
            return getattr(status, "value", str(status)) if status is not None else None
    return None


def _events_path(app, run_id: str) -> Path | None:
    logs_root = _logs_root(app)
    if logs_root is None:
        return None
    candidates = [logs_root / run_id / "events.jsonl"]
    thread_id = _thread_id_of_run(app, run_id)
    if thread_id:
        candidates.append(
            logs_root / "threads" / thread_id / "runs" / run_id / "events.jsonl"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def mount_status_routes(app: FastAPI) -> None:
    """Run 事件 + 状态端点挂载（main.create_app 内调用）。"""

    @app.get("/runs/{run_id}/events")
    def read_run_events(
        run_id: str,
        limit: int = Query(default=200, ge=1, le=2000),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        if getattr(app.state, "runtime", None) is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        events_path = _events_path(app, run_id)
        status = _status_of_run(app, run_id)
        if events_path is None and status is None:
            raise HTTPException(status_code=404, detail="run not found")

        events: list[RunEventView] = []
        if events_path is not None:
            try:
                text = events_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.exception("read run events failed (run %s)", run_id)
                raise HTTPException(
                    status_code=503, detail="run journal unreadable"
                ) from exc
            # RunJournal 落盘格式：json.dumps(..., indent=2) + "\n\n" 分隔
            # （多行 pretty JSON，空行分条）——不是每行一条 JSON
            for block in text.split("\n\n"):
                block = block.strip()
                if not block:
                    continue
                try:
                    raw = json.loads(block)
                except ValueError:
                    continue  # 损坏块跳过（journal append 期间的半条）
                events.append(run_event_view_from(_as_run_event(raw)))
            events = events[offset: offset + limit]

        return {"run_id": run_id, "status": status, "events": [e.model_dump() for e in events]}

    @app.get("/status", response_model=RuntimeStatus)
    def read_status() -> RuntimeStatus:
        runtime = getattr(app.state, "runtime", None)
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")
        return runtime_status_from_runtime(runtime)

    @app.get("/capabilities")
    def read_capabilities() -> dict:
        """能力三态矩阵 + 连通性（engram doctor 同源，只读、无密钥）。

        与 CLI doctor / TUI Ctrl+U 消费同一份 DoctorReport——Web 只做展示。
        探测含网络检查（秒级），同步端点跑线程池可接受；前端按需拉取。
        """
        from engram.backend.app.cli.doctor import build_report

        project_root = Path(__file__).resolve().parents[4]
        try:
            report = build_report(project_root)
        except Exception as exc:  # noqa: BLE001 - 端点绝不 500 裸栈
            logger.exception("capabilities report failed")
            raise HTTPException(status_code=503, detail=f"probe failed: {exc}") from exc
        payload = report.to_dict()
        payload["has_broken"] = report.has_broken
        return payload


class _AsRunEvent:
    """JSONL 行 → RunEvent 形态鸭子（run_event_view_from 读属性）。"""

    __slots__ = ("event_id", "run_id", "event_type", "payload", "created_at")

    def __init__(self, raw: dict) -> None:
        self.event_id = str(raw.get("event_id") or raw.get("id") or "")
        self.run_id = str(raw.get("run_id") or "")
        self.event_type = str(raw.get("event_type") or raw.get("type") or "")
        self.payload = raw.get("payload") or {}
        self.created_at = raw.get("created_at") or raw.get("timestamp")


def _as_run_event(raw: dict) -> _AsRunEvent:
    return _AsRunEvent(raw)
