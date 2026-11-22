"""GET /capabilities — doctor 同源能力矩阵（web-capabilities）。

验证：
- 端点返回 DoctorReport 结构（capabilities/connectivity/has_broken）
- build_report 失败 → 503 而非裸栈
- 响应不含任何密钥（红线：RuntimeStatus 同款）
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


def _fake_report():
    def result(key, label, state, detail, fix=""):
        return SimpleNamespace(key=key, label=label, state=state, detail=detail, fix=fix)

    def conn(key, label, state, detail):
        return SimpleNamespace(key=key, label=label, state=state, detail=detail)

    caps = (
        result("llm", "对话（LLM）", "on", "deepseek 端点可达"),
        result("mcp", "MCP 工具", "broken", "缺少 MCP 配置文件", "创建该文件"),
    )
    conns = (
        conn("llm", "LLM", "ok", "deepseek 端点可达"),
        conn("pg", "Postgres", "skipped", "未配置"),
    )
    report_dict = {
        "capabilities": [
            {"key": c.key, "label": c.label, "state": c.state, "detail": c.detail, "fix": c.fix}
            for c in caps
        ],
        "connectivity": [
            {"key": c.key, "label": c.label, "state": c.state, "detail": c.detail}
            for c in conns
        ],
    }
    report = SimpleNamespace(
        capabilities=caps, connectivity=conns,
        has_broken=True,
        to_dict=lambda: report_dict,
    )
    return report, report_dict, report.has_broken


def test_capabilities_returns_doctor_report(monkeypatch):
    report, report_dict, has_broken = _fake_report()
    monkeypatch.setattr(
        "engram.backend.app.cli.doctor.build_report", lambda root: report,
    )
    app = create_app(runtime_factory=lambda: object())
    client = TestClient(app)
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["has_broken"] is True
    assert payload["capabilities"][0]["key"] == "llm"
    assert payload["capabilities"][1]["state"] == "broken"
    assert payload["capabilities"][1]["fix"] == "创建该文件"
    assert payload["connectivity"][1]["state"] == "skipped"


def test_capabilities_probe_failure_is_503(monkeypatch):
    def _boom(_root):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr("engram.backend.app.cli.doctor.build_report", _boom)
    app = create_app(runtime_factory=lambda: object())
    client = TestClient(app)
    resp = client.get("/capabilities")
    assert resp.status_code == 503
    assert "probe failed" in resp.json()["detail"]


def test_capabilities_response_has_no_secrets(monkeypatch):
    report, report_dict, _ = _fake_report()
    monkeypatch.setattr(
        "engram.backend.app.cli.doctor.build_report", lambda root: report,
    )
    app = create_app(runtime_factory=lambda: object())
    client = TestClient(app)
    resp = client.get("/capabilities")
    text = resp.text.lower()
    for marker in ("api_key", "apikey", "sk-", "password", "authorization"):
        assert marker not in text
