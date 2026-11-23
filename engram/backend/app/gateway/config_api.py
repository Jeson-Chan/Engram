"""运行配置端点 — POST /config 与 POST /mcp/reload（web-config-surface）。

- POST /config {provider?, model?, expert_mode?}：复用 AppRuntime.switch_model /
  switch_expert_mode 重建模型路由与 leader graph，替换 app.state.runtime。
  作用域：网关全局（所有会话的后续运行），在途 SSE 继续用旧 graph 跑完。
- POST /mcp/reload：复用 AppRuntime.reload_mcp_tools 重建工具并替换运行时；
  MCP 模块未启用 → 503。

返回 {model, provider, mode, reloaded} 摘要；未知 provider → 400。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class ConfigRequest(BaseModel):
    """POST /config 请求体（字段全部可选；缺省字段表示不改动）。"""

    provider: str | None = None
    model: str | None = None
    expert_mode: bool | None = None


def mount_config_routes(app: FastAPI) -> None:
    """把配置端点挂到网关应用（main.create_app 内调用）。"""

    @app.post("/config")
    def apply_config(payload: ConfigRequest) -> dict:
        """应用模型/模式变更（网关全局；返回更新后的摘要）。"""
        runtime = app.state.runtime
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")

        # 1) 模型切换（先做：重建 capability_registry，模式切换在其结果上叠加）
        if payload.provider is not None:
            from engram.backend.agents.config.provider_config import (
                discover_available_providers,
            )

            available = {p.provider for p in discover_available_providers()}
            if payload.provider not in available:
                raise HTTPException(
                    status_code=400,
                    detail=f"provider '{payload.provider}' unavailable (no API key or disabled); "
                           f"available: {sorted(available)}",
                )
            try:
                runtime = runtime.switch_model(payload.provider, payload.model)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"model switch failed: {exc}") from exc
            app.state.runtime = runtime

        # 2) 模式切换（在（可能已更新的）运行时之上重建 leader graph）
        if payload.expert_mode is not None:
            current = bool(getattr(runtime.config.runtime, "expert_mode", False))
            if payload.expert_mode != current:
                try:
                    runtime = runtime.switch_expert_mode(payload.expert_mode)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"mode switch failed: {exc}") from exc
                app.state.runtime = runtime

        from engram.backend.app.gateway.views import runtime_status_from_runtime

        status = runtime_status_from_runtime(app.state.runtime)
        return {
            "model": status.model,
            "provider": status.provider,
            "mode": status.mode,
            "reloaded": True,
        }

    @app.post("/mcp/reload")
    def reload_mcp() -> dict:
        """重载 MCP 工具并重建 graph（MCP 模块未启用 → 503）。"""
        runtime = app.state.runtime
        if runtime is None:
            raise HTTPException(status_code=503, detail="agent runtime not ready")
        if getattr(runtime, "mcp_manager", None) is None:
            raise HTTPException(status_code=503, detail="mcp module not enabled")
        try:
            app.state.runtime = runtime.reload_mcp_tools()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"mcp reload failed: {exc}") from exc
        mgr = getattr(app.state.runtime, "mcp_manager", None)
        servers = list(mgr.list_servers()) if mgr is not None and hasattr(mgr, "list_servers") else []
        return {"reloaded": True, "mcp": servers}