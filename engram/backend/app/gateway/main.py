"""FastAPI 网关应用 — ASGI 入口，落在预留的 gateway 包。

startup（lifespan）做一次性重引导：模型路由 / MCP / 技能等重活
只在启动期做一次，请求处理路径零重建。runtime_factory 可注入，
测试传 stub 避免真实 provider/网络。

启动：uvicorn engram.backend.app.gateway.main:app
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from engram.backend.app.bootstrap import AppRuntime, bootstrap_runtime
from engram.backend.app.gateway.chat import mount_chat_routes
from engram.backend.app.gateway.registry import SessionRegistry
from engram.backend.app.schemas.sessions import SessionCreateRequest, SessionResponse
from engram.backend.agents.runtime.checkpointer import (
    reset_checkpointer,
    set_checkpointer,
)
from engram.backend.agents.runtime.pg_checkpointer import (
    close_pg_checkpointer,
    create_pg_checkpointer,
    pg_dsn_from_env,
)


def create_app(
    runtime_factory: Callable[[], AppRuntime] | None = None,
) -> FastAPI:
    """构建网关应用。

    runtime_factory=None → 生产路径用 bootstrap_runtime；
    测试注入 stub 工厂（lifespan 调用一次，供后续 chat/research 端点用）。
    SessionRegistry 在构造期创建（轻量纯内存），不依赖 lifespan 触发——
    不进 with 块的 TestClient 也能正常服务会话 CRUD。
    """
    factory = runtime_factory or bootstrap_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # PG 持久 checkpointer：DSN 配置时先异步建 saver（建表一次）并预装进
        # 单例槽位——随后 factory() 里的 make_lead_agent 编译 graph 拿到的就是它。
        # 进程重启读回同一会话状态；多 worker 各持独立池、共享同一 PG 会话表。
        pg_saver = None
        dsn = pg_dsn_from_env()
        if dsn:
            pg_saver = await create_pg_checkpointer(dsn)
            set_checkpointer(pg_saver)
        try:
            # 一次性重引导：重活（模型路由、MCP、技能）只发生在这里。
            app.state.runtime = factory()
            yield
        finally:
            if pg_saver is not None:
                await close_pg_checkpointer(pg_saver)
                reset_checkpointer()

    app = FastAPI(
        title="Engram Gateway",
        description="长期记忆研究 Agent 服务网关（会话 / 对话 / 研究接口）。",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.session_registry = SessionRegistry()
    mount_chat_routes(app)
    app.state.runtime = None  # lifespan 填充；会话 CRUD 不依赖它

    @app.post("/sessions", response_model=SessionResponse, status_code=201)
    def create_session(request: SessionCreateRequest | None = None) -> SessionResponse:
        """新建会话——分配独立 thread_id（会话间状态互不污染的作用域键）。
        无请求体可用（全默认值：default-user、无元数据）。"""
        request = request or SessionCreateRequest()
        record = app.state.session_registry.create(
            user_id=request.user_id,
            metadata=request.metadata,
        )
        return _to_response(record)

    @app.get("/sessions", response_model=list[SessionResponse])
    def list_sessions(user_id: str | None = None) -> list[SessionResponse]:
        """会话列表；?user_id= 过滤。"""
        return [
            _to_response(r)
            for r in app.state.session_registry.list(user_id=user_id)
        ]

    @app.get("/sessions/{session_id}", response_model=SessionResponse)
    def get_session(session_id: str) -> SessionResponse:
        record = app.state.session_registry.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return _to_response(record)

    @app.delete("/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str) -> None:
        deleted = app.state.session_registry.delete(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="session not found")

    return app


def _to_response(record) -> SessionResponse:
    return SessionResponse(
        session_id=record.session_id,
        thread_id=record.thread_id,
        user_id=record.user_id,
        created_at=record.created_at,
        status=record.status,
        metadata=record.metadata,
    )


# 模块级实例：uvicorn engram.backend.app.gateway.main:app 直接可用。
app = create_app()
