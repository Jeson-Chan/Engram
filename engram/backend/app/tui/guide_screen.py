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
class GuideField:
    """步骤内嵌输入字段（如 Tavily key、Redis URL）。"""

    env_key: str            # 写入 .env 的键
    placeholder: str        # 输入框占位提示
    default: str = ""       # 预填值（用户未编辑时也写入；留空语义由步骤自定）
    password: bool = False  # 掩码显示（密钥类）


@dataclass(frozen=True)
class GuideStep:
    """向导的一个功能步骤（声明式）。"""

    key: str                      # 稳定标识（用于探测映射与测试）
    title: str                    # 步骤标题
    description: str              # 这功能做什么
    effect: str                   # 开启后行为提示（成本/行为变化）
    env_key: str                  # 写入 .env 的主开关键
    on_value: str                 # 开启值
    off_value: str                # 关闭值（跳过时写显式关闭；空串=跳过不写键）
    probe_key: str | None         # probes 返回的键（None=无外部依赖）
    power_granting: bool = False  # 权力授予类：默认跳过 + 开启警示
    startup_only: bool = False    # 写入后需重启生效
    input_fields: tuple[GuideField, ...] = ()  # 开启时需填值的字段
    # 未开启/跳过时键的写入语义：
    #   off_value 非空 → 写显式关闭值（开关类原则）
    #   off_value 空 → 不写键（隐式默认类：分层记忆空值=默认 Markdown，
    #   写显式空串反而会覆盖 compose 注入）
    extra_probe_keys: tuple[str, ...] = ()     # 附加探测行（如分层记忆的 redis+pg）
    extra_write_keys: tuple[tuple[str, str], ...] = ()  # 附加写入键（值来自 input_fields）


GUIDE_STEPS: tuple[GuideStep, ...] = (
    GuideStep(
        key="tavily", title="Tavily 联网搜索",
        description="主搜索后端（结构化结果）；无 key 自动回退 DuckDuckGo。",
        effect="需要 TAVILY_API_KEY（免费额度即可）；不开启也总能搜。",
        env_key="TAVILY_API_KEY", on_value="", off_value="",
        probe_key="tavily",
        input_fields=(
            GuideField("TAVILY_API_KEY", "输入 TAVILY_API_KEY（回车确认，可留空稍后填）", password=True),
        ),
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
        key="memory_tier", title="分层记忆（热层/冷层）",
        description=(
            "热层(Redis)=读取加速（最近记忆秒回，越用越热）；"
            "冷层(Postgres)=永久沉淀（热层淘汰后的归宿）。"
            "默认 Markdown 单层，功能不受影响——这是可选提速/增强。"
        ),
        effect="写入两个连接串，重启后生效；不开启则保持 Markdown 单层。",
        env_key="ENGRAM_MEMORY_TIER", on_value="", off_value="",  # 占位主键不写入
        probe_key=None, startup_only=True,
        input_fields=(
            GuideField("ENGRAM_REDIS_URL", "Redis URL（留空=不启用热层）",
                       default="redis://localhost:6379/0"),
            GuideField("ENGRAM_MEMORY_PG_DSN", "Postgres DSN（留空=不启用冷层）",
                       default="postgresql://engram:engram@localhost:5432/engram"),
        ),
        extra_probe_keys=("redis", "pg"),
        extra_write_keys=(("ENGRAM_REDIS_URL", ""), ("ENGRAM_MEMORY_PG_DSN", "")),
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
        self._inputs: dict[str, str] = {}  # input 字段 env_key → 用户填的值
        self._input_field_index = 0  # 当前编辑的字段索引（多字段步骤内切换）
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
        # docker 部署会隐藏记忆层两步——步数收缩时当前索引不能越界
        self.step_index = min(self.step_index, self._summary_index())
        self._refresh_ui()

    def _is_docker(self) -> bool:
        """部署模式：docker 容器内 → 记忆层由 compose 注入，向导隐藏记忆两步。"""
        if self.probes is None:
            return False  # 探测未完成前按宿主机形态展示（步骤收缩后不影响已写入）
        dep = self.probes.get("deployment")
        return dep is not None and bool(getattr(dep, "available", False))

    def _visible_steps(self) -> list[GuideStep]:
        if self._is_docker():
            return [s for s in GUIDE_STEPS if s.key not in ("memory_tier", "memory", "phase2")]
        return list(GUIDE_STEPS)

    def _summary_index(self) -> int:
        return len(self._visible_steps())

    def _memory_effective(self) -> bool:
        """长期记忆生效态：显式开启，或随记忆沉淀自动带上（沉淀的上游依赖）。

        docker 部署下记忆由 compose 注入，此值不参与写入（记忆两步被隐藏）。
        """
        return self.choices["memory"] or self.choices["phase2"]

    # ---- 渲染 ----

    def _refresh_ui(self) -> None:
        title = self.query_one("#guide-title", Static)
        content = self.query_one("#guide-content", Static)
        foot = self.query_one("#guide-foot", Static)
        value_input = self.query_one("#guide-input", Input)
        steps = self._visible_steps()
        if self.step_index < self._summary_index():
            step = steps[self.step_index]
            title.update(Text(f"配置向导 {self.step_index + 1}/{self._summary_index()} · {step.title}"))
            content.update(self._render_step(step))
            foot.update(Text(
                "→ 下一步 · ← 上一步 · Enter 切换 开/跳过 · Esc 退出", style=theme.TEXT_DIM,
            ))
            # 开启且有输入字段 → 显示输入框并聚焦当前字段
            if self.choices[step.key] and step.input_fields:
                fields = step.input_fields
                self._input_field_index = min(self._input_field_index, len(fields) - 1)
                field = fields[self._input_field_index]
                value_input.display = True
                value_input.value = self._inputs.get(
                    field.env_key, field.default)
                value_input.placeholder = (
                    f"{field.env_key} · 字段 {self._input_field_index + 1}/{len(fields)}"
                    "（回车确认，→ 下一个字段）")
                value_input.password = field.password
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

    def _probe_line(self, probe_key: str, label: str) -> Text:
        """单个探测键的结论行。"""
        if self.probes is None:
            return Text(f"探测（{label}）：进行中…", style=theme.TEXT_DIM)
        result = self.probes.get(probe_key)
        if result is None:
            return Text(f"探测（{label}）：未执行", style=theme.TEXT_DIM)
        available = bool(getattr(result, "available", False))
        detail = str(getattr(result, "detail", ""))
        style = theme.TEXT_PRIMARY if available else "yellow"
        state = "就绪" if available else "未配置"
        return Text(f"探测（{label}）：{state} — {detail}", style=style)

    def _probe_text(self, step: GuideStep) -> Text:
        """该步骤的探测结论行（主探测 + 附加探测行）。"""
        extra = [self._probe_line(k, k) for k in step.extra_probe_keys]
        newline = chr(10)
        if extra and step.probe_key is None:
            return Text(newline).join(extra)
        if step.probe_key is None:
            return Text("探测：无外部依赖", style=theme.TEXT_DIM)
        main = self._probe_line(step.probe_key, step.probe_key)
        if extra:
            return Text(newline).join([main] + extra)
        return main

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
        if step.input_fields and enabled:
            for field in step.input_fields:
                value = self._inputs.get(field.env_key, field.default)
                if value:
                    lines.append(Text(
                        f"{field.env_key}：已填写（已隐藏）", style=theme.TEXT_DIM))
                else:
                    lines.append(Text(
                        f"{field.env_key}：未填（留空=不写此键）", style="yellow"))
            # 依赖不可达警示：开启也不会生效
            for pk in step.extra_probe_keys:
                probe = (self.probes or {}).get(pk)
                if probe is not None and not bool(getattr(probe, "available", False)):
                    lines.append(Text(
                        f"⚠ {pk} 不可达——开启也不会生效（可跳过此步）", style="yellow"))
                    break
        return Text("\n").join(lines)

    def _render_summary(self) -> Text:
        lines: list[Text] = [Text("将写入 .env："), Text("")]
        if self._is_docker():
            lines.append(Text(
                "docker 部署：记忆层（含沉淀开关）由 compose 注入，本向导不写记忆配置。",
                style=theme.TEXT_DIM,
            ))
            lines.append(Text(""))
        restart_items: list[str] = []   # 写入后需重启生效（startup_only）
        missing_key: list[str] = []     # 开启但 key 未填（写入空值，功能不生效）
        immediate: list[str] = []       # 即刻生效（非 startup_only 且值就绪）
        for step in self._visible_steps():
            on = self._memory_effective() if step.key == "memory" else self.choices[step.key]
            mark = Text("✓ 开启 ", style="green") if on else Text("○ 跳过 ", style=theme.TEXT_DIM)
            line = Text()
            line.append(mark)
            line.append(f"{step.title}  {step.env_key}=")
            if step.key == "memory_tier":
                # 分层记忆汇总：列出各字段值；跳过整行 dim 且不写键
                if on:
                    for field in step.input_fields:
                        value = self._inputs.get(field.env_key, field.default)
                        if not value:
                            missing_key.append(f"{step.title}·{field.env_key}")
                        lines.append(Text(
                            f"{mark.plain if hasattr(mark, 'plain') else ''}{step.title}  "
                            f"{field.env_key}={value or chr(34)*2}", style=theme.TEXT_DIM))
                    restart_items.append(step.title)
                else:
                    lines.append(Text(
                        f"○ 跳过 {step.title}（保持 Markdown 单层，不写键）", style=theme.TEXT_DIM))
                continue
            value = step.on_value if on else step.off_value
            if on and step.input_fields:
                value = self._inputs.get(step.input_fields[0].env_key, step.input_fields[0].default)
                if not value:
                    missing_key.append(step.title)
            line.append(Text(value if value else '""', style=theme.TEXT_DIM))
            lines.append(line)
            if on and step.startup_only:
                restart_items.append(step.title)
            elif on and not step.input_fields:
                immediate.append(step.title)
            elif on and step.input_fields and all(
                self._inputs.get(f.env_key, f.default) for f in step.input_fields
            ):
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
        summary_index = self._summary_index()
        if self.step_index <= summary_index:
            event.stop()
        if event.key == "enter":
            if self.step_index < summary_index:
                step = self._visible_steps()[self.step_index]
                self.choices[step.key] = not self.choices[step.key]
                self._refresh_ui()
            else:
                self._write_env()
                self.dismiss(True)
        elif event.key == "right" or event.key == "down":
            self.step_index = min(summary_index, self.step_index + 1)
            self._refresh_ui()
        elif event.key == "left" or event.key == "up":
            self.step_index = max(0, self.step_index - 1)
            self._refresh_ui()

    def on_input_changed(self, event: Input.Changed) -> None:
        """输入实时存值（写入时收集；按当前字段路由）。"""
        steps = self._visible_steps()
        step = steps[self.step_index] if self.step_index < len(steps) else None
        if step is not None and step.input_fields:
            field = step.input_fields[
                min(self._input_field_index, len(step.input_fields) - 1)]
            self._inputs[field.env_key] = event.value.strip()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 确认当前字段：还有后续字段→切下一个；末字段→焦点还屏
        （否则 → 翻页被 Input 吃掉，用户困在本步）。"""
        steps = self._visible_steps()
        step = steps[self.step_index] if self.step_index < len(steps) else None
        if step is not None and step.input_fields:
            if self._input_field_index < len(step.input_fields) - 1:
                self._input_field_index += 1
                self._refresh_ui()
                return
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
        for step in self._visible_steps():
            on = self._memory_effective() if step.key == "memory" else self.choices[step.key]
            if step.key == "memory_tier":
                # 分层记忆：开启且字段有值 → 写该键；留空 → 不写（隐式默认
                # Markdown——显式空串会覆盖 compose 注入，反显式性）。
                if on:
                    for field in step.input_fields:
                        value = self._inputs.get(field.env_key, field.default)
                        if value:
                            overrides[field.env_key] = value
                continue
            value = step.on_value if on else step.off_value
            if on and step.input_fields:
                value = self._inputs.get(
                    step.input_fields[0].env_key, step.input_fields[0].default)
            overrides[step.env_key] = value
        update_env_file(self._env_path, overrides, create=True)
        load_dotenv(self._env_path, override=True)
        self.written = True

    def action_dismiss_panel(self) -> None:
        self.dismiss(False)
