"""Engram TUI 统一主题色板。

配色决策（2026-11-20 像素风重构定案，tui-pixel-flavor change）：

1. **基底 = logo 血缘锚定**：BG #0e1012 与 logo 实测底色同源（向 GitHub
   wordmark 靠），SURFACE/SURFACE_ALT 按等差亮度重排。深灰微冷、
   无蓝紫色偏的旧原则保留。
2. **紫 = roguelike 洋红紫（#a63fc0，Dwarf Fortress 一脉）**：UI 语义紫
   从 SaaS 蓝紫 #7c6ff0 换为饱和洋红侧，与青/橙的冷亮色形成
   "用户侧重色、agent 侧亮色"层次。青 #45c4b8（agent 侧）、橙 #FF8C42
   （执行态）语义不变。banner 渐变起点 #7C6FF0 **不动**——banner 是
   logo 资产复刻（品牌 display 色），与 UI 语义色分属两套系统；
   青端不变，渐变叙事"紫青两端"仍成立。
3. **执行状态保留橙色**（#FF8C42）：暖色相标记动态执行，冷色相标记
   静态角色——信息设计不变，随像素风味级重构（docs/design/pixel-flavor-spec.md）。

各 widget 模块从此处导入色值，禁止再散落硬编码 hex，保证全局一致。
"""

from __future__ import annotations

# ---- 基底：纯中性灰阶，深灰→浅灰过渡，不带色偏 ----
BG = "#0e1012"              # 背景：中性深灰
SURFACE = "#16181b"          # 卡片/输入框填充：比背景亮一档的中性灰
SURFACE_ALT = "#1e2124"     # 次级填充（状态行/信息行/侧面板背景）：再亮一档

# ---- 边框：中性灰，比背景亮，给出清晰边界 ----
BORDER = "#3a3a3a"
BORDER_FOCUS = "#a63fc0"    # 聚焦态改用强调色，仅此一处用彩色边框

# ---- 文本：中性灰阶，不带色偏 ----
TEXT_PRIMARY = "#e8e8e8"    # 主文本（用户输入/回答正文）：足够亮
TEXT_SECONDARY = "#a0a0a0"  # 次要文本（标签/说明）
TEXT_DIM = "#6e6e6e"        # 弱化文本（版本号/次级提示）

# ---- 强调色（分层但收敛，不铺满全屏） ----
ACCENT_USER = "#a63fc0"        # 用户消息左竖线：明亮蓝紫
ACCENT_ASSISTANT = "#45c4b8"   # 助手消息左竖线：青绿，和用户区分
ACCENT_BRAND = "#b96fd0"       # 品牌强调（副标题/面板标题）
ACCENT_THOUGHT = "#FF8C42"     # 思考态：保留原橙色（执行状态色不变）
ACCENT_WARN = "#f0a868"        # 临界值提醒：暖橙，不用刺眼红
TOOL_BLUE = "#5aa9f5"          # 工具调用行强调

# ---- 面板明细标记色（语义分层，收敛在同一冷色家族） ----
MARK_WINDOW = "#5aa9f5"
MARK_MODEL = "#45c4b8"
MARK_MODE = "#b96fd0"
MARK_MCP = "#f0c05a"
MARK_FREE = "#6fce8a"

# ---- 进度条 ----
BAR_FILL = "#a63fc0"
BAR_EMPTY = "#2c2c2c"
