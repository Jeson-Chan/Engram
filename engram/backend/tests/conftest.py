"""测试根 conftest — 全局隔离。

两件事：

1. 会话库隔离：网关会话持久化（E2E 缺陷 F 修复，默认 SQLite
   .engram/gateway.db）之后，任何 create_app 的测试若不隔离会互相看见
   对方创建的会话。autouse fixture 把会话库指向每测试独立的 tmp 路径。

2. .env 剥离：仓库根若存在真实 .env（演示/开发用，含 ENGRAM_REDIS_URL
   等），gateway.main 导入期的 load_dotenv 会把它灌进测试进程——记忆/
   沙箱/skill 测试随之走真连接或不同实现路径（顺序性红测试）。测试基线
   是"无 .env"的密封环境：每测试剥掉这些键（monkeypatch 自动还原）。
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    # 防呆默认：个别收集期导入 main 的路径也不会碰真实 .engram/gateway.db
    os.environ.setdefault("ENGRAM_GATEWAY_DB", "memory")


# gateway.main 的 load_dotenv 会从仓库根 .env 注入的运行时键（测试密封基线=全部缺席）
_DOTENV_RUNTIME_KEYS = (
    "ENGRAM_REDIS_URL",
    "ENGRAM_MEMORY_PG_DSN",
    "ENGRAM_MEMORY_TTL_SECONDS",
    "ENGRAM_CHECKPOINT_DSN",
    "ENGRAM_PG_DSN",
    "ENGRAM_RUNS_PG_DSN",
    "ENGRAM_MEMORY_USE",
    "ENGRAM_MEMORY_PHASE2_ENABLED",
    "ENGRAM_SKILL_ENABLED",
    "ENGRAM_SANDBOX_USE",
    "ENGRAM_SANDBOX_ALLOW_HOST_BASH",
    "ENGRAM_MCP_ENABLED",
    "ENGRAM_MULTIAGENT_ENABLED",
)


@pytest.fixture(autouse=True)
def _hermetic_runtime_env(monkeypatch, tmp_path):
    """每测试：剥离 .env 注入的运行时键 + 独立 SQLite 会话库。"""
    for key in _DOTENV_RUNTIME_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENGRAM_GATEWAY_DB", str(tmp_path / "gateway.db"))
    yield
