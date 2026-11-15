<div align="center">

<!-- IMAGE SLOT: hero banner -->

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
cp .env.example .env
```

打开 `.env`，填入 `DEEPSEEK_API_KEY=sk-...`。

## 快速开始

**Windows（PowerShell）**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn engram.backend.app.gateway.main:app --port 8000
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn engram.backend.app.gateway.main:app --port 8000
```

**Docker（一条命令全起）**

```bash
cp .env.example .env    # 填入 DEEPSEEK_API_KEY
docker compose up -d
```

打开 http://localhost:8000/docs 在浏览器里直接试接口，或者在终端里开一个会话：

```bash
curl -X POST localhost:8000/sessions
curl -N -X POST localhost:8000/sessions/<session_id>/chat -H "Content-Type: application/json" -d '{"message": "你好"}'
```

想用终端应用？运行 `engram`。

## 许可证

[MIT](LICENSE)
