"""tui-command-surface 回归 — /guide 向导 + 命令面收敛（/exit、/clear、Ctrl+P 移除）。

覆盖 spec `tui-guide` / `tui-interaction`：
- 向导分步顺序、Enter 开/跳过切换、中途 Esc 退出不写入
- 探测注入的就绪/未配置文案
- 汇总写入 .env（跳过项写显式关闭值、未提及键保留）、startup-only 重启提示
- 权力授予默认跳过 + 显式开启路径
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App
from textual.containers import Container

from engram.backend.app.tui.guide_screen import GUIDE_STEPS, GuideScreen


class _GuideHost(App):
    """承载向导的最小宿主。"""

    def __init__(self, screen_factory) -> None:
        super().__init__()
        self._factory = screen_factory
        self.dismissed: list = []

    def compose(self):
        yield Container()

    def on_mount(self) -> None:
        self.push_screen(self._factory(), callback=self._record)

    def _record(self, result) -> None:
        self.dismissed.append(result)


def _probes(mcp_ok: bool = False, docker_ok: bool = False, tavily_ok: bool = False,
            redis_ok: bool = False, pg_ok: bool = False):
    def result(name, ok, detail=""):
        return SimpleNamespace(available=ok, detail=detail or f"{name} state")

    return {
        "tavily": result("tavily", tavily_ok),
        "mcp_config": result("mcp", mcp_ok, "缺少 .engram/mcp_servers.yaml"),
        "docker": result("docker", docker_ok, "Docker 29.0.1"),
        "deployment": result("deployment", docker_ok,
                             "docker 容器内" if docker_ok else "宿主机直跑（venv）"),
        "redis": result("redis", redis_ok, "Redis 可达" if redis_ok else "6379 不可达"),
        "pg": result("pg", pg_ok, "Postgres 可达" if pg_ok else "5432 不可达"),
    }


async def _step_count(screen) -> int:
    return len(GUIDE_STEPS)


def _content(screen) -> str:
    from textual.widgets import Static

    return str(screen.query_one("#guide-content", Static).render())


def test_guide_step_order_and_defaults():
    """步骤固定顺序（Tavily→Skill→MCP→沙箱→巩固）；全部默认跳过；权力授予步预选跳过。"""
    assert [s.key for s in GUIDE_STEPS] == ["tavily", "skill", "mcp", "sandbox", "memory_tier", "memory", "phase2"]
    assert [s.power_granting for s in GUIDE_STEPS] == [False, False, True, True, False, False, False]
    assert [s.startup_only for s in GUIDE_STEPS] == [False, True, True, True, True, True, True]

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(Path("nonexistent.env"), probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.choices == {s.key: s.key == "memory" for s in GUIDE_STEPS}  # 长期记忆默认开启

    asyncio.run(check())


def test_guide_probe_states_rendered():
    """就绪/未配置两态文案 + 无外部依赖文案。"""

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(
            Path("nonexistent.env"),
            probes=_probes(mcp_ok=False, docker_ok=True),
        ))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 第 1 步 Tavily：未配置
            content = _content(screen)
            assert "未配置" in content or "TAVILY" in content
            # 跳到第 3 步 MCP（未配置，含原因）
            screen.step_index = 2
            screen._refresh_ui()
            content = _content(screen)
            assert "未配置" in content and "mcp_servers.yaml" in content
            # 第 4 步 沙箱（docker 就绪）
            screen.step_index = 3
            screen._refresh_ui()
            content = _content(screen)
            assert "就绪" in content
            # 第 2 步 Skill：无外部依赖
            screen.step_index = 1
            screen._refresh_ui()
            assert "无外部依赖" in _content(screen)

    asyncio.run(check())


def test_guide_enter_toggles_choice_and_power_warning():
    """Enter 切换 开↔跳过；MCP 步开启时文案含权力授予警示（红色）。"""

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(Path("nonexistent.env"), probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 第 1 步（Tavily，非权力授予）：Enter → 开启
            await pilot.press("enter")
            await pilot.pause()
            assert screen.choices["tavily"] is True
            content = _content(screen)
            assert "[ 开启 ]" in content and "权力授予" not in content
            # 跳到 MCP 步：Enter → 开启（带警示）
            screen.step_index = 2
            screen._refresh_ui()  # 切步收起 Tavily 输入框、焦点回屏
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert screen.choices["mcp"] is True
            content = _content(screen)
            assert "权力授予" in content
            assert "需重启生效" in content  # startup-only 提示

    asyncio.run(check())


def test_guide_esc_midway_writes_nothing(tmp_path: Path):
    """中途 Esc 退出：.env 不被写入（无文件）。"""
    env = tmp_path / ".env"

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("enter")   # 开启第 1 步
            await pilot.pause()
            await pilot.press("escape")  # 中途退出
            await pilot.pause()
            assert app.dismissed == [False]
            assert screen_written(app) is False

    def screen_written(app) -> bool:
        return getattr(app.screen, "written", False)

    asyncio.run(check())
    assert not env.exists()


def test_phase2_forces_memory_on_at_write(tmp_path: Path, monkeypatch):
    """记忆沉淀开启 → 写入时自动带上 ENGRAM_MEMORY_USE=default（上游依赖）。

    回归：此前 /guide 只写 PHASE2_ENABLED=true 不写 MEMORY_USE，
    doctor 报 broken"Phase 2 已开启但记忆主 Provider 未启用"。
    """
    import os

    env = tmp_path / ".env"
    for step in GUIDE_STEPS:
        monkeypatch.setenv(step.env_key, "orig")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "orig")

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 用户关掉长期记忆，只开沉淀
            screen.choices["memory"] = False
            screen.choices["phase2"] = True
            screen.step_index = len(GUIDE_STEPS)
            screen._refresh_ui()
            content = _content(screen)
            assert "✓ 开启" in content  # 汇总里长期记忆显示为开启（随沉淀带上）
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "ENGRAM_MEMORY_PHASE2_ENABLED=true" in text
    assert "ENGRAM_MEMORY_USE=default" in text  # 依赖自动补上


def test_memory_defaults_on_in_wizard(tmp_path: Path):
    """长期记忆默认开启（只读类核心功能）；其余默认跳过。"""

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(Path("nonexistent.env"), probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.choices["memory"] is True
            assert screen.choices["tavily"] is False
            assert screen.choices["mcp"] is False

    asyncio.run(check())


def test_guide_summary_writes_env(tmp_path: Path):
    """汇总确认：开启项写 on 值、跳过项写显式关闭值、未提及键保留。"""
    env = tmp_path / ".env"
    env.write_text(
        "DEEPSEEK_API_KEY=sk-keep\n"
        "ENGRAM_SKILL_ENABLED=false\n"
        "ENGRAM_MEMORY_USE=default\n",
        encoding="utf-8",
    )

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 开启 skill（第 2 步）与 sandbox（第 4 步）
            screen.step_index = 1
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()
            screen.step_index = 3
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()
            # 到汇总步
            screen.step_index = len(GUIDE_STEPS)
            screen._refresh_ui()
            content = _content(screen)
            # 汇总列出 startup-only 重启提示（sandbox 开了）
            assert "需重启生效" in content
            assert "沙箱" in content
            # 确认写入
            await pilot.press("enter")
            await pilot.pause()
            assert app.dismissed == [True]

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-keep" in text            # 未提及键保留
    assert "ENGRAM_MEMORY_USE=default" in text           # 未提及键保留
    assert "ENGRAM_SKILL_ENABLED=true" in text           # 开启项
    assert "ENGRAM_MCP_ENABLED=false" in text            # 跳过项写显式关闭值
    assert "ENGRAM_SANDBOX_USE=" in text                 # 开启项（Local provider 路径）
    assert "engram.backend.agents.sandbox.local" in text
    assert "TAVILY_API_KEY=" in text                     # tavily 跳过（关闭值空串）


def test_guide_summary_cancel_writes_nothing(tmp_path: Path):
    """汇总步 Esc 取消：.env 保持原内容。"""
    env = tmp_path / ".env"
    original = "SENTINEL=1\n"
    env.write_text(original, encoding="utf-8")

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.step_index = len(GUIDE_STEPS)
            screen._refresh_ui()
            await pilot.press("escape")
            await pilot.pause()
            assert app.dismissed == [False]

    asyncio.run(check())
    assert env.read_text(encoding="utf-8") == original


def test_guide_power_granting_not_explicitly_enabled_stays_off(tmp_path: Path):
    """权力授予步未显式开启（直接下一步）→ 写入保持关闭。"""
    env = tmp_path / ".env"

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 一路"下一步"到汇总（不开任何项）
            for _ in range(len(GUIDE_STEPS)):
                await pilot.press("right")
                await pilot.pause()
            # 汇总确认
            await pilot.press("enter")
            await pilot.pause()
            assert app.dismissed == [True]

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "ENGRAM_MCP_ENABLED=false" in text
    assert "ENGRAM_SANDBOX_USE=" in text  # 关闭值（空）


def test_guide_opens_via_handle_command():
    """真实 EngramTUI._handle_command 路径：/guide 回车打开向导。

    回归：0351556 曾在此路径漏 import pathlib.Path，/guide 一回车即 NameError
    崩溃退出（单测全走最小宿主 push GuideScreen，没覆盖 _handle_command）。
    """
    import asyncio
    from types import SimpleNamespace
    from textual.screen import ModalScreen

    from engram.backend.agents.capabilities.registry import CapabilityRegistry
    from engram.backend.app.tui.app import EngramTUI

    def _runtime() -> SimpleNamespace:
        return SimpleNamespace(
            thread_id="t-guide",
            config=SimpleNamespace(runtime=SimpleNamespace(
                expert_mode=False,
                logs_root=".engram/test-logs",
                timezone="UTC",
                plan_enabled=False,
            )),
            capability_registry=CapabilityRegistry(models={}),
            mcp_manager=None,
        )

    async def check() -> None:
        app = EngramTUI(runtime=_runtime())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            from engram.backend.app.tui.app import ConversationInput
            inp = app.query_one("#welcome-input", ConversationInput)
            inp.focus()
            await pilot.pause()
            inp.text = "/guide"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, GuideScreen), (
                f"/guide 未打开向导，当前屏：{type(app.screen).__name__}"
            )
            # 真实 on_key：切换选择 + 翻页不崩
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()

    asyncio.run(check())


def test_tavily_step_collects_api_key(tmp_path: Path, monkeypatch):
    """Tavily 步开启后显示输入框；填入的 key 写入 .env 与进程环境。"""
    import os

    env = tmp_path / ".env"
    # load_dotenv(override=True) 会把 tmp .env 的键灌进进程 env——
    # monkeypatch 记录原值，teardown 自动还原，避免污染其他测试
    for step in GUIDE_STEPS:
        monkeypatch.setenv(step.env_key, "orig")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "orig")

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes(tavily_ok=True)))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            # 第 1 步 Tavily：Enter 开启 → 输入框出现并聚焦
            await pilot.press("enter")
            await pilot.pause()
            value_input = screen.query_one("#guide-input")
            assert value_input.display is True
            # 在输入框里填 key（Input 有焦点时屏级 on_key 不拦截）
            value_input.value = "tvly-test-123"
            await pilot.pause()
            assert screen._inputs.get("TAVILY_API_KEY") == "tvly-test-123"
            # Input 提交后焦点归还屏（Enter 确认填值的交互）
            await pilot.press("enter")
            await pilot.pause()
            assert not value_input.has_focus
            # 翻到汇总确认写入
            screen.step_index = len(GUIDE_STEPS)
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()
            assert app.dismissed == [True]

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "TAVILY_API_KEY=tvly-test-123" in text
    # 进程环境已刷新（即刻生效的机制）
    assert os.environ.get("TAVILY_API_KEY") == "tvly-test-123"


def test_guide_write_refreshes_process_env(tmp_path: Path, monkeypatch):
    """写入后 load_dotenv(override=True)：Ctrl+U/doctor 读 os.environ 能看到新值。"""
    import os

    env = tmp_path / ".env"
    for step in GUIDE_STEPS:
        monkeypatch.setenv(step.env_key, "orig")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "orig")

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.step_index = 1  # skill
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()
            screen.step_index = len(GUIDE_STEPS)
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(check())
    assert os.environ.get("ENGRAM_SKILL_ENABLED") == "true"


def test_docker_deployment_hides_memory_steps(tmp_path: Path):
    """docker 部署：记忆两步从向导隐藏；确认写入不含记忆键。"""
    import os

    env = tmp_path / ".env"
    probes = _probes(docker_ok=True)  # helper 里 docker_ok → deployment=docker

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=probes))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            keys = [s.key for s in screen._visible_steps()]
            assert "memory" not in keys and "phase2" not in keys
            assert "memory_tier" not in keys
            assert "tavily" in keys and "mcp" in keys
            # 汇总提示 docker 注记
            screen.step_index = screen._summary_index()
            screen._refresh_ui()
            content = _content(screen)
            assert "compose 注入" in content
            # 确认写入
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "ENGRAM_MEMORY_USE" not in text
    assert "ENGRAM_MEMORY_PHASE2_ENABLED" not in text


def test_memory_tier_step_visible_venv_and_writes(tmp_path: Path, monkeypatch):
    """2.2/2.3：venv 展示分层记忆步骤；开启填值写入两键 + 重启清单。"""
    import os

    env = tmp_path / ".env"
    for step in GUIDE_STEPS:
        monkeypatch.setenv(step.env_key, "orig")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "orig")
    for extra in ("ENGRAM_REDIS_URL", "ENGRAM_MEMORY_PG_DSN"):
        monkeypatch.setenv(extra, "orig")

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes(
            redis_ok=True, pg_ok=True, docker_ok=False,
        )))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            keys = [s.key for s in screen._visible_steps()]
            assert "memory_tier" in keys
            # 开启分层记忆（步骤索引 4）
            screen.step_index = 4
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()
            assert screen.choices["memory_tier"] is True
            # 填两个字段：第一个字段（Redis）
            value_input = screen.query_one("#guide-input")
            value_input.value = "redis://localhost:6379/9"
            await pilot.pause()
            # Enter 提交第一字段 → 切第二字段
            await pilot.press("enter")
            await pilot.pause()
            value_input.value = "postgresql://engram:engram@localhost:5433/engram"
            await pilot.pause()
            # Enter 提交第二字段（末字段 → 焦点还屏）
            await pilot.press("enter")
            await pilot.pause()
            # 到汇总确认
            screen.step_index = screen._summary_index()
            screen._refresh_ui()
            content = _content(screen)
            assert "分层记忆" in content and "ENGRAM_REDIS_URL" in content
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "ENGRAM_REDIS_URL=redis://localhost:6379/9" in text
    assert "ENGRAM_MEMORY_PG_DSN=postgresql://engram:engram@localhost:5433/engram" in text


def test_memory_tier_skip_writes_no_keys(tmp_path: Path, monkeypatch):
    """2.3：跳过分层记忆 → 两个键都不写（隐式默认 Markdown）。"""
    env = tmp_path / ".env"

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(env, probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.step_index = screen._summary_index()
            screen._refresh_ui()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(check())
    text = env.read_text(encoding="utf-8")
    assert "ENGRAM_REDIS_URL" not in text
    assert "ENGRAM_MEMORY_PG_DSN" not in text


def test_memory_tier_unreachable_dep_warns(tmp_path: Path):
    """2.2：依赖不可达 → 步骤内黄字"开启也不会生效"。"""
    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(Path("nonexistent.env"), probes=_probes(
            redis_ok=False, pg_ok=False,
        )))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.step_index = 4  # memory_tier
            screen.choices["memory_tier"] = True
            screen._refresh_ui()
            content = _content(screen)
            assert "不可达" in content and "不会生效" in content

    asyncio.run(check())


def test_ctrl_p_binding_removed_from_tui():
    """Ctrl+P 绑定已从 EngramTUI 移除。"""
    from engram.backend.app.tui.app import EngramTUI

    keys = {b.key for b in EngramTUI.BINDINGS}
    assert "ctrl+p" not in keys
