"""Web UI 挂载测试 — gateway-client-api / 兼容与错误语义（任务 4.5）。

验证：
- flag 关闭（默认）：零 web 路由，`/app` 404，网关行为不变
- flag 开启 + 产物存在：`/app` 返回 index，静态资源可取，
  未知前端路由回退 index（SPA history fallback）
- flag 开启但产物缺失：不挂载（warning，不崩）
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


@pytest.fixture()
def fake_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<html><body>ENGRAM WEB</body></html>", encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    return dist


def _client():
    app = create_app(runtime_factory=lambda: object())
    return TestClient(app), app


def test_disabled_by_default_no_web_routes():
    client, _ = _client()
    with client as c:
        assert c.get("/app").status_code == 404
        assert c.get("/app/some/route").status_code == 404
        # 既有端点不受影响
        assert c.get("/sessions").status_code == 200


def test_enabled_serves_index_and_fallback(fake_dist, monkeypatch):
    monkeypatch.setenv("ENGRAM_WEB_UI_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_WEB_UI_DIST", str(fake_dist))
    # dist 外的敏感文件：穿越目标
    secret = fake_dist.parent / "secret.env"
    secret.write_text("API_KEY=leaked", encoding="utf-8")
    client, _ = _client()
    with client as c:
        index = c.get("/app")
        assert index.status_code == 200
        assert "ENGRAM WEB" in index.text

        # 静态资源
        js = c.get("/app/assets/app.js")
        assert js.status_code == 200
        assert "console.log" in js.text

        # 未知前端路由回退 index（SPA history fallback）
        fallback = c.get("/app/sessions/some-id/inspector")
        assert fallback.status_code == 200
        assert "ENGRAM WEB" in fallback.text

        # 路径穿越（review critical）：.. 编码 / 绝对路径都不读 dist 外文件。
        # 行为两种都安全：路由层不匹配 → 404；路由匹配 → 回退 index。
        # 红线只有一条：不泄漏 secret.env / win.ini 内容。
        for evil in ("/app/%2e%2e/%2e%2e/secret.env", "/app/../../secret.env",
                     "/app/..%2f..%2fsecret.env", "/app//etc/passwd",
                     "/app/C:/Windows/win.ini"):
            resp = c.get(evil)
            assert resp.status_code in (200, 404)
            assert "leaked" not in resp.text and "win.ini" not in resp.text
            if resp.status_code == 200:
                assert "ENGRAM WEB" in resp.text  # 是 index 回退

        # 既有端点不受影响
        assert c.get("/sessions").status_code == 200


def test_enabled_but_missing_dist_no_mount(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGRAM_WEB_UI_ENABLED", "true")
    monkeypatch.setenv("ENGRAM_WEB_UI_DIST", str(tmp_path / "nonexistent"))
    client, _ = _client()
    with client as c:
        assert c.get("/app").status_code == 404  # 未挂载，但不崩


def test_real_web_dist_mounted_when_present(monkeypatch):
    """仓库内真实 web/dist（任务 5.1 之后）：flag 开启即挂载。"""
    project_root = Path(__file__).parents[6]
    dist = project_root / "web" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("web/dist not built yet (task 5.1)")
    monkeypatch.setenv("ENGRAM_WEB_UI_ENABLED", "true")
    client, _ = _client()
    with client as c:
        assert "html" in c.get("/app").text.lower()
