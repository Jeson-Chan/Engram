"""GuideScreen — /guide 分步配置向导（tui-command-surface）。

设计（design.md D2）：单 ModalScreen 内部步骤状态机，非多 Screen 串联——
Esc 始终一层 dismiss（中途退出不写入）。步骤数据声明式定义：
功能项（key/标题/说明/env 键/默认/权力授予标记/startup-only 标记），
渲染与写入逻辑通用。

- 探测（D3）：on_mount 时 thread worker 执行 probe_all 一次，结果缓存到
  向导实例；各步显示 就绪/未配置+原因。
- 选择（D4）：Enter 在 开↔跳过 间切换（权力授予类默认跳过，开启时文案
  红色警示）；汇总步列出全部选择，Enter 确认写入 / Esc 取消不写入。
- 写入（D5）：update_env_file（保留未提及键）；跳过项写显式关闭值——
  `.env` 是探测报告，不留隐式状态。完成提示列出 startup-only 清单。

TUI 内不能 input() 阻塞问答（冻死事件循环）——engram init 的交互
代码不可复用，这里是它的 Textual 化实现，探测与写盘逻辑同源。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from engram.backend.app.tui import theme

_LOCAL_SANDBOX = (
    "engram.backend.agents.sandbox.local.local_sandbox_provider:LocalSandboxProvider"
)


@dataclass(frozen=True)
class GuideStep:
    """向导的一个功能步骤（声明式）。"""

    key: str                      # 稳定标识（用于探测映射与测试）
    title: str                    # 步骤标题
    description: str              # 这功能做什么
    effect: str                   # 开启后行为提示（成本/行为变化）
    env_key: str                  # 写入 .env 的键
    on_value: str                 # 开启值
    off_value: str                # 关闭值（跳过时写显式关闭）
    probe_key: str | None         # probes 返回的键（None=无外部依赖）
    power_granting: bool = False  # 权力授予类：默认跳过 + 开启警示
    startup_only: bool = False    # 写入后需重启生效
    input_env: str | None = None  # 开启时需要用户填值的 env 键（如 Tavily key）


GUIDE_STEPS: tuple[GuideStep, ...] = (
    GuideStep(
        key="tavily", title="Tavily 联网搜索",
        description="主搜索后端（结构化结果）；无 key 自动回退 DuckDuckGo。",
        effect="需要 TAVILY_API_KEY（免费额度即可）；不开启也总能搜。",
        env_key="TAVILY_API_KEY", on_value="", off_value="",
        probe_key="tavily", input_env="TAVILY_API_KEY",
    ),
    GuideStep(
        key="skill", title="Skill 注入",
        description="按需把 skill 文档注入上下文（只读类，依赖就位即安全）。",
        effect="无外部依赖；注入会占少量上下文 token。",
        env_key="ENGRAM_SKILL_ENABLED", on_value="true", off_value="false",
        probe_key=None, startup_only=True,
    ),
    GuideStep(
        key="mcp", title="MCP 工具",
        description="加载外部 MCP server 提供的工具集。",
        effect="权力授予：MCP server 可执行任意 npm 包代码；需 .engram/mcp_servers.yaml。",
        env_key="ENGRAM_MCP_ENABLED", on_value="true", off_value="false",
        probe_key="mcp_config", power_granting=True, startup_only=True,
    ),
    GuideStep(
        key="sandbox", title="沙箱",
        description="隔离执行命令/脚本（bash、代码运行）。",
        effect="权力授予：Local 沙箱在宿主机执行命令（无隔离）；开启后需重启生效。",
        env_key="ENGRAM_SANDBOX_USE", on_value=_LOCAL_SANDBOX, off_value="",
        probe_key="docker", power_granting=True, startup_only=True,
    ),
    GuideStep(
        key="memory", title="长期记忆",
        description="跨会话记住对话内容（Markdown/分层存储，只读类）。",
        effect="记忆沉淀（后台巩固）依赖此项：没有它，沉淀没有写入对象。",
        env_key="ENGRAM_MEMORY_USE", on_value="default", off_value="",
        probe_key=None, startup_only=True,
    ),
    GuideStep(
        key="phase2", title="自动记忆沉淀（后台巩固）",
        description="每 N 轮自动抽取 + 巩固长期记忆；依赖长期记忆——开启将自动带上。",
        effect="会产生额外 LLM 调用（成本）；默认关闭，属 opt-in。",
        env_key="ENGRAM_MEMORY_PHASE2_ENABLED", on_value="true", off_value="false",
        probe_key=None, startup_only=True,
    ),
)

_STEP_COUNT = len(GUIDE_STEPS)
# 汇总步索引 = 全部功能步之后
_SUMMARY_INDEX = _STEP_COUNT


class GuideScreen(ModalScreen[bool]):
    """/guide 分步向导：↑↓/Enter 操作，Esc 任意时刻退出（不写入）。"""

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close", show=False, priority=True),
    ]

    DEFAULT_CSS = f"""
    GuideScreen {{ align: center middle; background: $background 60%; }}
    GuideScreen > #guide-box {{
        width: 72; max-width: 90%;
        height: auto; max-height: 80%;
        background: {theme.SURFACE};
        border: tall {theme.BORDER};
        padding: 1 2;
    }}
    #guide-title {{ color: {theme.ACCENT_BRAND}; margin-bottom: 0; }}
    #guide-hint {{ color: {theme.TEXT_DIM}; margin-bottom: 1; }}
    #guide-body {{ height: auto; }}
    #guide-input {{ display: none; height: 3; margin-top: 1; }}
    #guide-foot {{ margin-top: 1; color: {theme.TEXT_DIM}; }}
    """

    def __init__(self, env_path: Path, probes: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._env_path = env_path
        # 注入探测结果（测试）；None=on_mount 时 worker 执行 probe_all
        self._probes_injected = probes
        self.probes: dict[str, Any] | None = probes
        self.step_index = 0          # 0..N-1 功能步；N = 汇总步
        # 长期记忆默认开启（只读类，核心功能）；其余默认跳过
        self.choices: dict[str, bool] = {s.key: s.key == "memory" for s in GUIDE_STEPS}
        self._inputs: dict[str, str] = {}  # input_env → 用户填的值（Tavily key 等）
        self.written = False         # 汇总确认后置 True（测试可读）

    def compose(self) -> ComposeResult:
        with Vertical(id="guide-box"):
            yield Static("", id="guide-title")
            yield Static("Enter 切换 开/跳过 · → 下一步 · Esc 退出（不写入）", id="guide-hint")
            with VerticalScroll(id="guide-body"):
                yield Static("", id="guide-content")
            yield Input(placeholder="TAVILY_API_KEY", password=True, id="guide-input")
            yield Static("", id="guide-foot")

    def on_mount(self) -> None:
        self._refresh_ui()
        if self._probes_injected is None:
            self.run_worker(self._run_probes, thread=True, exclusive=True)

    def _run_probes(self) -> None:
        from engram.backend.app.cli.probes import probe_all

        results = probe_all(self._env_path.parent)
        self.app.call_from_thread(self._probes_done, results)

    def _probes_done(self, results: dict[str, Any]) -> None:
        self.probes = results
        self._refresh_ui()

    def _memory_effective(self) -> bool:
        """长期记忆生效态：显式开启，或随记忆沉淀自动带上（沉淀的上游依赖）。"""
        return self.choices["memory"] or self.choices["phase2"]

    # ---- 渲染 ----

    def _refresh_ui(self) -> None:
        title = self.query_one("#guide-title", Static)
        content = self.query_one("#guide-content", Static)
        foot = self.query_one("#guide-foot", Static)
        value_input = self.query_one("#guide-input", Input)
        if self.step_index < _STEP_COUNT:
            step = GUIDE_STEPS[self.step_index]
            title.update(Text(f"配置向导 {self.step_index + 1}/{_STEP_COUNT} · {step.title}"))
            content.update(self._render_step(step))
            foot.update(Text(
                "→ 下一步 · ← 上一步 · Enter 切换 开/跳过 · Esc 退出", style=theme.TEXT_DIM,
            ))
            # 开启且需要填值（如 Tavily key）→ 显示输入框并聚焦
            if self.choices[step.key] and step.input_env:
                value_input.display = True
                value_input.value = self._inputs.get(step.input_env, "")
                value_input.placeholder = f"输入 {step.input_env}（回车确认，可留空稍后填）"
                value_input.focus()
            else:
                value_input.display = False
        else:
            title.update(Text("配置向导 · 汇总"))
            content.update(self._render_summary())
            foot.update(Text(
                "Enter 确认写入 .env · Esc 取消（不写入）", style=theme.TEXT_DIM,
            ))
            value_input.display = False

    def _probe_text(self, step: GuideStep) -> Text:
        """该步骤的探测结论行。"""
        if step.probe_key is None:
            return Text("探测：无外部依赖", style=theme.TEXT_DIM)
        if self.probes is None:
            return Text("探测：进行中…", style=theme.TEXT_DIM)
        result = self.probes.get(step.probe_key)
        if result is None:
            return Text("探测：未执行", style=theme.TEXT_DIM)
        available = bool(getattr(result, "available", False))
        detail = str(getattr(result, "detail", ""))
        style = theme.TEXT_PRIMARY if available else "yellow"
        state = "就绪" if available else "未配置"
        return Text(f"探测：{state} — {detail}", style=style)

    def _render_step(self, step: GuideStep) -> Text:
        lines: list[Text] = [
            Text(step.description),
            Text(""),
            self._probe_text(step),
            Text(""),
            Text(f"开启后：{step.effect}"),
            Text(""),
        ]
        enabled = self.choices[step.key]
        if enabled:
            if step.power_granting:
                lines.append(Text(
                    "选择：[ 开启 ] 跳过   ⚠ 权力授予：该功能将获得上述能力，请确认信任",
                    style="red",
                ))
            else:
                lines.append(Text("选择：[ 开启 ] 跳过", style="green"))
        else:
            lines.append(Text("选择：  开启 [ 跳过 ]", style=theme.TEXT_DIM))
        if step.startup_only:
            lines.append(Text("（此项写入后需重启生效）", style="yellow"))
        if step.input_env and enabled:
            filled = self._inputs.get(step.input_env, "")
            if filled:
                lines.append(Text(f"{step.input_env}：已填写（已隐藏）", style=theme.TEXT_DIM))
            else:
                lines.append(Text(
                    f"请在下方输入框填入 {step.input_env}（可留空稍后填；空值写入后功能不生效）",
                    style="yellow",
                ))
        return Text("\n").join(lines)

    def _render_summary(self) -> Text:
        lines: list[Text] = [Text("将写入 .env："), Text("")]
        restart_items: list[str] = []   # 写入后需重启生效（startup_only）
        missing_key: list[str] = []     # 开启但 key 未填（写入空值，功能不生效）
        immediate: list[str] = []       # 即刻生效（非 startup_only 且值就绪）
        for step in GUIDE_STEPS:
            on = self._memory_effective() if step.key == "memory" else self.choices[step.key]
            mark = Text("✓ 开启 ", style="green") if on else Text("○ 跳过 ", style=theme.TEXT_DIM)
            line = Text()
            line.append(mark)
            line.append(f"{step.title}  {step.env_key}=")
            value = step.on_value if on else step.off_value
            if on and step.input_env:
                value = self._inputs.get(step.input_env, "")
                if not value:
                    missing_key.append(step.title)
            line.append(Text(value if value else '""', style=theme.TEXT_DIM))
            lines.append(line)
            if on and step.startup_only:
                restart_items.append(step.title)
            elif on and step.input_env is None:
                immediate.append(step.title)
            elif on and step.input_env and self._inputs.get(step.input_env):
                immediate.append(step.title)
        lines.append(Text(""))
        if missing_key:
            lines.append(Text(
                f"⚠ 已开启但未填值：{'、'.join(missing_key)}——功能在填值前不会生效",
                style="yellow",
            ))
        if restart_items:
            lines.append(Text(f"需重启生效：{'、'.join(restart_items)}", style="yellow"))
        if immediate:
            lines.append(Text(f"即刻生效：{'、'.join(immediate)}", style="green"))
        lines.append(Text("（未提及的键保持原值）", style=theme.TEXT_DIM))
        return Text("\n").join(lines)

    # ---- 键处理 ----

    async def on_key(self, event: events.Key) -> None:
        # 输入框持有焦点时（如填 Tavily key）按键归 Input，不触发向导切换
        if isinstance(self.app.focused, Input):
            return
        if event.key == "escape":
            return  # 走 BINDINGS dismiss_panel
        if self.step_index <= _SUMMARY_INDEX:
            event.stop()
        if event.key == "enter":
            if self.step_index < _STEP_COUNT:
                step = GUIDE_STEPS[self.step_index]
                self.choices[step.key] = not self.choices[step.key]
                self._refresh_ui()
            else:
                self._write_env()
                self.dismiss(True)
        elif event.key == "right" or event.key == "down":
            self.step_index = min(_SUMMARY_INDEX, self.step_index + 1)
            self._refresh_ui()
        elif event.key == "left" or event.key == "up":
            self.step_index = max(0, self.step_index - 1)
            self._refresh_ui()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Tavily key 等输入实时存值（写入时收集）。"""
        step = GUIDE_STEPS[self.step_index] if self.step_index < _STEP_COUNT else None
        if step is not None and step.input_env:
            self._inputs[step.input_env] = event.value.strip()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 确认填值并把焦点还给屏——否则 → 翻页被 Input 吃掉，用户困在本步。"""
        self.app.set_focus(None)

    def _write_env(self) -> None:
        """汇总确认 → 写 .env（跳过项写显式关闭值；未提及键保留）+ 刷新进程环境。

        load_dotenv(override=True) 与 SettingsScreen 同款：Tavily 等每次调用
        直读 os.environ 的功能即刻生效；startup-only 项仍需重启（完成提示
        会列出清单——Ctrl+U 显示的是运行态，restart 项在重启前保持 off）。
        """
        from dotenv import load_dotenv
        from engram.backend.app.cli.setup_wizard import update_env_file

        overrides: dict[str, str] = {}
        for step in GUIDE_STEPS:
            on = self._memory_effective() if step.key == "memory" else self.choices[step.key]
            value = step.on_value if on else step.off_value
            if on and step.input_env:
                value = self._inputs.get(step.input_env, "")
            overrides[step.env_key] = value
        update_env_file(self._env_path, overrides, create=True)
        load_dotenv(self._env_path, override=True)
        self.written = True

    def action_dismiss_panel(self) -> None:
        self.dismiss(False)
