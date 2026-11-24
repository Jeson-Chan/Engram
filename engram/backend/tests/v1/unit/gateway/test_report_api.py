"""surface-parity — POST /sessions/{id}/report 外部行为。"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(logs_root=".engram/logs", expert_mode=False),
            reporting=SimpleNamespace(save_artifact=False),
            sandbox=None,
        ),
        researcher_model_name="m",
        leader_agent=SimpleNamespace(graph=SimpleNamespace()),
        capability_registry=SimpleNamespace(),
        thread_dir="/tmp/unused",
    )


def _client(runtime) -> TestClient:
    return TestClient(create_app(runtime_factory=lambda: runtime))


def _create_session(client: TestClient) -> str:
    return client.post("/sessions").json()["session_id"]


def test_report_success(monkeypatch, tmp_path) -> None:
    import engram.backend.agents.reporting as reporting

    monkeypatch.setattr(
        reporting, "generate_report_from_thread",
        lambda runtime, topic=None: SimpleNamespace(
            artifact_path=str(tmp_path / "r.md"), final_report="# 报告内容",
        ),
    )
    rt = _runtime()
    rt.config.runtime.logs_root = str(tmp_path / "logs")
    with _client(rt) as client:
        sid = _create_session(client)
        resp = client.post(f"/sessions/{sid}/report", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_report"] == "# 报告内容"
    assert body["artifact_path"].endswith("r.md")


def test_report_unknown_session_404() -> None:
    with _client(_runtime()) as client:
        resp = client.post("/sessions/nope/report", json={})
    assert resp.status_code == 404


def test_report_runtime_missing_503(monkeypatch) -> None:
    with _client(None) as client:
        sid = _create_session(client)
        resp = client.post(f"/sessions/{sid}/report", json={})
    assert resp.status_code == 503


def test_report_failure_500_type_only(monkeypatch, tmp_path) -> None:
    import engram.backend.agents.reporting as reporting

    def _boom(runtime, topic=None):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(reporting, "generate_report_from_thread", _boom)
    rt = _runtime()
    rt.config.runtime.logs_root = str(tmp_path / "logs")
    with _client(rt) as client:
        sid = _create_session(client)
        resp = client.post(f"/sessions/{sid}/report", json={})
    assert resp.status_code == 500
    assert "RuntimeError" in resp.json()["detail"]
    assert "secret detail" not in resp.json()["detail"]