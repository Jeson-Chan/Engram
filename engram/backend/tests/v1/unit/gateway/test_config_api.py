"""web-config-surface — POST /config 与 POST /mcp/reload 外部行为。

- /config：模式切换、模型切换、未知 provider 400、runtime 未就绪 503
- /mcp/reload：成功重建并返回列表、无 mcp_manager 503
- /status：models 候选字段
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


def _runtime(expert_mode: bool = False, model: str = "m0", mcp_manager=None, skill_manager=None):
    rt = SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(expert_mode=expert_mode),
            sandbox=None,
        ),
        researcher_model_name=model,
        skill_manager=skill_manager,
        mcp_manager=mcp_manager,
    )

    def switch_expert_mode(value: bool):
        return _runtime(expert_mode=value, model=model, mcp_manager=mcp_manager, skill_manager=skill_manager)

    def switch_model(provider: str, model_name: str | None = None):
        return _runtime(expert_mode=expert_mode, model=f"{provider}/{model_name or 'default'}",
                        mcp_manager=mcp_manager, skill_manager=skill_manager)

    def reload_mcp_tools():
        return _runtime(expert_mode=expert_mode, model=model, mcp_manager=mcp_manager, skill_manager=skill_manager)

    rt.switch_expert_mode = switch_expert_mode
    rt.switch_model = switch_model
    rt.reload_mcp_tools = reload_mcp_tools
    return rt


def _client(runtime) -> TestClient:
    return TestClient(create_app(runtime_factory=lambda: runtime))


def test_apply_mode_switch(monkeypatch) -> None:
    rt = _runtime(expert_mode=False)
    with _client(rt) as client:
        resp = client.post("/config", json={"expert_mode": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "expert"
    assert body["reloaded"] is True


def test_apply_model_switch(monkeypatch) -> None:
    rt = _runtime()
    # discover_available_providers 白名单（避免依赖真实 .env）
    from engram.backend.agents.config import provider_config as pc

    monkeypatch.setattr(
        pc, "discover_available_providers",
        lambda: [SimpleNamespace(provider="qwen", model="qwen-plus")],
    )
    with _client(rt) as client:
        resp = client.post("/config", json={"provider": "qwen", "model": "qwen-plus"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "qwen/qwen-plus"


def test_apply_unknown_provider_400(monkeypatch) -> None:
    rt = _runtime()
    from engram.backend.agents.config import provider_config as pc

    monkeypatch.setattr(pc, "discover_available_providers", lambda: [])
    with _client(rt) as client:
        resp = client.post("/config", json={"provider": "nope"})
    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"]


def test_config_runtime_not_ready_503() -> None:
    with _client(None) as client:
        # runtime_factory 返回 None → lifespan 填充 None
        resp = client.post("/config", json={"expert_mode": True})
    assert resp.status_code == 503


def test_mcp_reload_success() -> None:
    mgr = SimpleNamespace(list_servers=lambda: [{"name": "local", "transport": "stdio"}])
    rt = _runtime(mcp_manager=mgr)
    with _client(rt) as client:
        resp = client.post("/mcp/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reloaded"] is True
    assert body["mcp"][0]["name"] == "local"


def test_mcp_reload_without_manager_503() -> None:
    rt = _runtime(mcp_manager=None)
    with _client(rt) as client:
        resp = client.post("/mcp/reload")
    assert resp.status_code == 503


def test_status_includes_models(monkeypatch) -> None:
    from engram.backend.agents.config import provider_config as pc

    monkeypatch.setattr(
        pc, "discover_available_providers",
        lambda: [SimpleNamespace(provider="openai", model="gpt", default=True)],
    )
    rt = _runtime()
    with _client(rt) as client:
        resp = client.get("/status")
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert models and models[0]["provider"] == "openai"