"""FastAPI 网关应用 — ASGI 入口，落在预留的 gateway 包。

startup（lifespan）做一次性重引导：模型路由 / MCP / 技能等重活
只在启动期做一次，请求处理路径零重建。runtime_factory 可注入，
测试传 stub 避免真实 provider/网络。

启动：uvicorn engram.backend.app.gateway.main:app
"""

from __future__ import annotations

import asyncio

# 与 CLI 同款：从项目根加载 .env（uvicorn 不读它——README 的
# pip 快速开始路线要求网关进程自己拿 DEEPSEEK_API_KEY 等配置）
from pathlib import Path as _Path

from dotenv import load_dotenv

load_dotenv(_Path(__file__).resolve().parents[4] / ".env")  # parents: gateway/app/backend/engram/项目根

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from engram.backend.app.bootstrap import AppRuntime, bootstrap_runtime
from engram.backend.app.gateway.chat import mount_chat_routes
from engram.backend.app.gateway.history import mount_history_routes
from engram.backend.app.gateway.memory_api import mount_memory_routes
from engram.backend.app.gateway.registry import SessionRegistry
from engram.backend.app.gateway.status_api import mount_status_routes
from engram.backend.app.gateway.web_ui import mount_web_ui
from engram.backend.app.gateway.research import mount_research_routes
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
            # E2E 缺陷 A 兜底在 create_pg_checkpointer 内（建池前秒级失败，
            # 可操作提示）；推荐入口 python -m engram.backend.app.gateway
            # 已保证 win32 Selector 策略。
            pg_saver = await create_pg_checkpointer(dsn)
            set_checkpointer(pg_saver)
        # 运行历史持久层（issue 09）：复用 checkpointer DSN 或独立
        # ENGRAM_RUNS_PG_DSN；未配任何 PG 时历史端点 503（CRUD/chat 不受影响）
        run_store = None
        import os

        runs_dsn = (
            os.environ.get("ENGRAM_RUNS_PG_DSN", "").strip()
            or dsn
        )
        if runs_dsn:
            from engram.backend.agents.runtime.pg_run_store import PGRunStore

            # 构造失败（坏 DSN / DB 不可达）也要清理已建的 saver 池并复位
            # 单例，否则半启动状态泄漏（review）
            try:
                run_store = await asyncio.to_thread(PGRunStore, runs_dsn)
            except Exception:
                if pg_saver is not None:
                    await close_pg_checkpointer(pg_saver)
                    reset_checkpointer()
                raise
        app.state.run_store = run_store
        try:
            # 一次性重引导：重活（模型路由、MCP、技能）只发生在这里。
            app.state.runtime = factory()
            yield
        finally:
            if run_store is not None:
                await asyncio.to_thread(run_store.close)
            if pg_saver is not None:
                await close_pg_checkpointer(pg_saver)
                reset_checkpointer()

    app = FastAPI(
        title="Engram Gateway",
        description="长期记忆研究 Agent 服务网关（会话 / 对话 / 研究接口）。",
        version="0.1.0",
        lifespan=lifespan,
    )
    # E2E 缺陷 F：会话映射持久化（默认 SQLite .engram/gateway.db，WAL；
    # ENGRAM_GATEWAY_DB 可覆盖路径，=memory 显式不落盘）。重启后
    # GET /sessions 仍返回旧会话，session_id 仍可解析到原 thread。
    from engram.backend.app.gateway.session_store import build_default_session_store

    app.state.session_registry = SessionRegistry(store=build_default_session_store())
    mount_chat_routes(app)
    mount_research_routes(app)
    mount_history_routes(app)
    mount_memory_routes(app)
    mount_status_routes(app)
    app.state.runtime = None  # lifespan 填充；会话 CRUD 不依赖它
    app.state.run_store = None  # lifespan 填充（PG 配置时）
    # SSE 断线重连缓冲（issue 10）：per-session 事件环形缓冲
    from engram.backend.app.gateway.sse_buffer import SessionEventBuffers

    app.state.sse_buffers = SessionEventBuffers()

    # Web 工作台静态挂载（feature flag，默认关——迁移计划 3：
    # 关闭/产物缺失时零路由注册，网关行为不变）
    mount_web_ui(app)

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
        # 同步释放该会话的 SSE 事件缓冲（review：此前 500 帧 deque 永驻进程）
        app.state.sse_buffers.drop(session_id)

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
