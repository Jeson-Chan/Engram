"""测试根 conftest — 全局隔离。

网关会话持久化（E2E 缺陷 F 修复，默认 SQLite .engram/gateway.db）之后，
任何 create_app 的测试若不隔离会互相看见对方创建的会话（精确计数断言
碎裂、顺序耦合）。autouse fixture 把会话库指向每测试独立的 tmp 路径。
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    # 防呆默认：个别收集期导入 main 的路径也不会碰真实 .engram/gateway.db
    os.environ.setdefault("ENGRAM_GATEWAY_DB", "memory")


@pytest.fixture(autouse=True)
def _isolated_gateway_db(tmp_path, monkeypatch):
    """每测试独立 SQLite 会话库（真实持久语义也在 tmp 里验证）。"""
    monkeypatch.setenv("ENGRAM_GATEWAY_DB", str(tmp_path / "gateway.db"))
    yield
