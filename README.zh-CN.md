<div align="center">

<p><img src="docs/assets/engram-logo.gif" alt="ENGRAM" width="640" /></p>

# Engram

一个记得住你的研究助手。它作为一个小型 Web 服务跑起来：提一个问题，看着答案流出来；隔天再回来，它还记得你们在聊什么，服务重启过、快缓存清空过，都没关系。

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent%201.x-5aa9e5?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![Redis](https://img.shields.io/badge/Redis-hot%20cache-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-memory-4169E1?style=for-the-badge)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?style=for-the-badge)](https://www.docker.com/)

简体中文 · [English](README.md) · [日本語](README.ja.md)

</div>

---

## 功能特性

- **实时对话** —— 推理和搜索的过程、答案文本，边发生边显示，不用对着加载图标干等
- **研究模式** —— 一个问题变成一份流式报告，随时回来翻看
- **长期记忆** —— 会话经得起重启；快缓存清空了也不丢东西
- **断线不丢进度** —— 连接断了，重连接着上次的位置继续
- **也能在终端用** —— 自带全屏 TUI 和 CLI（`engram`）

## Demo

## 安装

需要 Python 3.12+ 和一个 DeepSeek API key（任何 OpenAI 兼容服务也行）。

```bash
git clone https://github.com/Jeson-Chan/Engram.git
cd Engram
pip install -e ".[dev]"
```

## 快速开始

```powershell
engram
```

首次启动会问 API key（或先运行 `engram init`）。就这么多——TUI 自包含：
对话、记忆、Skill 全在进程内跑，不需要任何后端或 Docker。`engram doctor`
可做可选体检（能力矩阵 + 连通性）。

驾驶舱里：

| 快捷键 | 作用 |
|---|---|
| `Ctrl+K` | 会话切换 / 新建会话 |
| `Ctrl+O` | Run 时间线（运行历史 + 持久事件） |
| `Ctrl+G` | Memory 面板（热/冷/遗忘计数） |
| `Ctrl+U` | Inspector（模型/模式/能力 + 运行环境） |
| `Esc` | 关闭任何弹层 |

## Web 工作台

先构建一次前端，然后选后端启动方式。两种都行；区别在记忆层形态和
配置改动的生效方式。

```powershell
cd web
npm install
npm run build
cd ..
```

### 本地起后端（venv）

跑在你的 Python 环境里。默认 Markdown 单层记忆；要分层可配 Redis/PG
（TUI 里 `/guide` 有引导步骤）。`.env` 配置改动需重启网关进程。

bash / zsh：

```bash
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
```

PowerShell：

```powershell
$env:ENGRAM_WEB_UI_ENABLED = "true"
python -m engram.backend.app.gateway --port 8000
```

cmd：

```cmd
set ENGRAM_WEB_UI_ENABLED=true
python -m engram.backend.app.gateway --port 8000
```

### docker 起后端

```bash
docker compose up -d
```

记忆分层（Redis 热层 / Postgres 冷层）由 compose 注入，`.env` 无需配 DSN。
配置改动需重建容器（`docker compose up -d --build`）——镜像内烧死代码，
且分层 DSN 永远 compose 优先于 `.env`。

两种方式工作台都在 `http://localhost:8000/app`。

## 已知限制

- 内置 `web_search`（DuckDuckGo）需要出网访问 DuckDuckGo；受限网络下返回空结果。研究链路不依赖它——使用本地沙箱与预置记忆。
- Docker sandbox 为可选项；未安装 `agent-sandbox` 时网关使用 `LocalSandboxProvider`。

## 许可证

[MIT](LICENSE)
