# Web 研究工作台使用说明（任务 5.8）

三栏研究工作台：会话栏 / 流式对话与研究 / Run Inspector（含 Memory Explorer）。
终端入口（CLI/TUI）不受 Web 影响——`ENGRAM_WEB_UI_ENABLED` 默认关。

## 启动

```bash
# 1) 构建前端（仓库 web/）
cd web
npm install
npm run build            # 产物 → web/dist

# 2) 起网关（Windows 用安全入口；带 Web）
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000

# 3) 打开
http://127.0.0.1:8000/app
```

开发模式（热更新，代理到网关 8000）：`cd web && npm run dev` → `http://127.0.0.1:5173`。

预置演示数据（幂等 seed）：`python -m engram.backend.app.demo.seed`。

## 界面速览

| 区域 | 能看到什么 |
|---|---|
| 左栏会话列表 | 标题/用户/时间；点选切换，`+ 新建会话`，删除幂等 |
| 中间对话区 | token 级流式回答；工具卡片（参数/结果/耗时/成败）；召回记忆提示（可展开 id/score/strength）；上下文预算条；流内错误横幅 |
| 右栏 Run Inspector | 本会话运行历史（状态/时间/token）；事件时间线（run/LLM/工具/记忆/报告）；报告预览与下载 |
| 右栏 Memory Explorer | 全部/热层/冷层/遗忘/巩固计数；按文本/类型/强度/层筛选；强度条 |

窄屏（<900px）：会话栏与 Inspector 收为抽屉按钮，对话区与输入框保持完整可用。

## 快捷键 / 交互

- `Enter` 发送，`Shift+Enter` 换行；模式切换：对话 / 研究。
- 刷新页面自动恢复：选中会话写进 URL `?s=`，历史消息与最近 Run 回放。
- SSE 断线：自动携带 `Last-Event-ID` 重连补发；缺口超缓冲 → 顶部红色提示
  「部分事件丢失…建议重开会话或运行」，不静默拼接。

## 演示截图 / GIF 生成步骤

截图（放进 `docs/assets/`，README 引用）：

```bash
python -m engram.backend.app.demo.seed   # 预置演示数据
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
# 浏览器打开 http://127.0.0.1:8000/app 依次截图：
#  1. 三栏全貌（宽视口）——选 seed 会话「上周的 LangGraph 记忆研究」
#  2. 流式研究一轮——工具卡片展开 + 召回提示展开
#  3. Memory Explorer——筛选 semantic + 强度条
#  4. 窄视口抽屉形态（浏览器缩窄 <900px）
#  5. 断线提示（DevTools Network → 断流）或刷新恢复前后对照
```

GIF（演示动图）：

```bash
# Windows：用 ScreenToGif（Microsoft Store）框选浏览器区域录制 30-45s：
# 流式研究 → 工具卡片 → Memory 筛选 → 刷新恢复；导出 docs/assets/demo.gif
```

## 测试

```bash
cd web
npm run test      # Vitest：SSE 解析契约（直接解析 docs/event-semantics.md 的示例块）
                  #        + 三栏壳/响应式组件测试
npm run build     # tsc -b + vite build（类型检查 + 产物）
npm run e2e       # Playwright smoke（需先 seed（python -m engram.backend.app.demo.seed）
                  # 并按上文起网关；用系统 Edge 通道，免下载浏览器二进制）
```
