"""Skill 管理端点 — GET /skills 与 POST /skills/{skill_id}/enabled。

web-skill-override：web 面板的数据源与启停入口。
- 列表：SkillManager.list_skills()（含 enabled 字段），模块未启用 → 空数组
- 启停：store.set_enabled（运行时持久、跨重启），未知名 → 404，
  skill 模块未启用 → 503（明确不可用，不 500）
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class SkillEnabledRequest(BaseModel):
    """POST /skills/{skill_id}/enabled 请求体。"""

    enabled: bool


def mount_skill_routes(app: FastAPI) -> None:
    """把 skill 管理端点挂到网关应用（main.create_app 内调用）。"""

    @app.get("/skills")
    def list_skills() -> list[dict]:
        """激活 skill 列表（含 enabled）。skill 模块未启用 → 空数组。"""
        runtime = app.state.runtime
        mgr = getattr(runtime, "skill_manager", None) if runtime is not None else None
        if mgr is None or not hasattr(mgr, "list_skills"):
            return []
        try:
            return list(mgr.list_skills())
        except Exception:
            return []

    @app.post("/skills/{skill_id}/enabled")
    def set_skill_enabled(skill_id: str, payload: SkillEnabledRequest) -> dict:
        """启用/禁用单个 skill（运行时持久，跨重启生效）。"""
        runtime = app.state.runtime
        mgr = getattr(runtime, "skill_manager", None) if runtime is not None else None
        if mgr is None or not hasattr(mgr, "store") or not hasattr(mgr.store, "set_enabled"):
            raise HTTPException(status_code=503, detail="skill module not enabled")
        if not mgr.store.set_enabled(skill_id, payload.enabled):
            raise HTTPException(status_code=404, detail="skill not found")
        return {"skill_id": skill_id, "enabled": payload.enabled}
