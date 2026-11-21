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


def _probes(mcp_ok: bool = False, docker_ok: bool = False, tavily_ok: bool = False):
    def result(name, ok, detail=""):
        return SimpleNamespace(available=ok, detail=detail or f"{name} state")

    return {
        "tavily": result("tavily", tavily_ok),
        "mcp_config": result("mcp", mcp_ok, "缺少 .engram/mcp_servers.yaml"),
        "docker": result("docker", docker_ok, "Docker 29.0.1"),
    }


async def _step_count(screen) -> int:
    return len(GUIDE_STEPS)


def _content(screen) -> str:
    from textual.widgets import Static

    return str(screen.query_one("#guide-content", Static).render())


def test_guide_step_order_and_defaults():
    """步骤固定顺序（Tavily→Skill→MCP→沙箱→巩固）；全部默认跳过；权力授予步预选跳过。"""
    assert [s.key for s in GUIDE_STEPS] == ["tavily", "skill", "mcp", "sandbox", "phase2"]
    assert [s.power_granting for s in GUIDE_STEPS] == [False, False, True, True, False]
    assert [s.startup_only for s in GUIDE_STEPS] == [False, False, True, True, False]

    async def check() -> None:
        app = _GuideHost(lambda: GuideScreen(Path("nonexistent.env"), probes=_probes()))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.choices == {s.key: False for s in GUIDE_STEPS}

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


def test_ctrl_p_binding_removed_from_tui():
    """Ctrl+P 绑定已从 EngramTUI 移除。"""
    from engram.backend.app.tui.app import EngramTUI

    keys = {b.key for b in EngramTUI.BINDINGS}
    assert "ctrl+p" not in keys
