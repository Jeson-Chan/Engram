"""网关层会话 CRUD 外部行为测试 — HTTP 语义，不测内部实现。

- 生命周期：bootstrap 工厂 startup 只调一次，多请求不再触发
- 隔离：每会话独立 thread_id
- CRUD：创建 / 列表（含 user_id 过滤）/ 详情 / 删除的 201/200/204/404
- Swagger：/docs 可访问（面试现场即兴演示的入口）
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from engram.backend.app.gateway.main import create_app


def _client_with_counting_factory(calls: list) -> TestClient:
    """App + 计数 stub 工厂（lifespan 调一次 bootstrap_runtime 的替身）。"""
    def factory():
        calls.append(1)
        return object()  # 会话 CRUD 不依赖 runtime；stub 足够
    return TestClient(create_app(runtime_factory=factory))


def test_bootstrap_runs_once_not_per_request() -> None:
    """重引导只在 startup 发生一次；N 个请求不触发 N 次。"""
    calls: list = []
    with _client_with_counting_factory(calls) as client:
        for _ in range(5):
            client.post("/sessions")
            client.get("/sessions")
    assert len(calls) == 1


def test_create_session_returns_ids() -> None:
    """POST /sessions → 201 + session_id/thread_id/user_id/created_at。"""
    with _client_with_counting_factory([]) as client:
        resp = client.post("/sessions", json={"user_id": "alice", "metadata": {"topic": "demo"}})
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"]
    assert body["thread_id"].startswith("thread-")  # agent 侧作用域键格式
    assert body["user_id"] == "alice"
    assert body["created_at"]
    assert body["metadata"] == {"topic": "demo"}


def test_sessions_have_independent_threads() -> None:
    """两个会话各拿独立 thread_id——会话间状态互不污染的前提。"""
    with _client_with_counting_factory([]) as client:
        first = client.post("/sessions").json()
        second = client.post("/sessions").json()
    assert first["thread_id"] != second["thread_id"]
    assert first["session_id"] != second["session_id"]


def test_list_sessions_and_user_filter() -> None:
    with _client_with_counting_factory([]) as client:
        client.post("/sessions", json={"user_id": "alice"})
        client.post("/sessions", json={"user_id": "bob"})
        all_sessions = client.get("/sessions").json()
        alice_only = client.get("/sessions", params={"user_id": "alice"}).json()
    assert len(all_sessions) == 2
    assert len(alice_only) == 1 and alice_only[0]["user_id"] == "alice"


def test_get_session_detail_and_404() -> None:
    with _client_with_counting_factory([]) as client:
        created = client.post("/sessions").json()
        found = client.get(f"/sessions/{created['session_id']}")
        missing = client.get("/sessions/sess-does-not-exist")
    assert found.status_code == 200
    assert found.json()["session_id"] == created["session_id"]
    assert missing.status_code == 404


def test_delete_session_flow() -> None:
    with _client_with_counting_factory([]) as client:
        created = client.post("/sessions").json()
        sid = created["session_id"]
        assert client.delete(f"/sessions/{sid}").status_code == 204
        assert client.get(f"/sessions/{sid}").status_code == 404
        # 重复删除 → 404
        assert client.delete(f"/sessions/{sid}").status_code == 404
        # 删除后列表不再包含
        assert all(s["session_id"] != sid for s in client.get("/sessions").json())


def test_swagger_docs_available() -> None:
    """面试现场打开 /docs 即兴演示——文档页必须可用。"""
    with _client_with_counting_factory([]) as client:
        assert client.get("/docs").status_code == 200
        spec = client.get("/openapi.json").json()
    assert "/sessions" in spec["paths"]
