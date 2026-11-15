<div align="center">

<!-- IMAGE SLOT: hero banner（在此插入新主视觉图 —— 如 docs/assets/hero.png） -->

# Engram

**一个会记住你的研究助手 —— 网络断了也不丢进度。**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-快缓存-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-永久记忆-4169E1?style=for-the-badge)](https://www.postgresql.org/)

**简体中文** · [English](README.md) · [日本語](README.ja.md)

动态字标：[logo/standalone.html](logo/standalone.html) —— 字母化作记忆细胞，一道光每隔几秒扫过：一次记忆被唤起。

</div>

---

## 这是一个什么

Engram 是一个跑在你自己电脑上的 AI 研究助手，以一个小型 Web 服务的形式提供。创建一个会话、问一个问题，答案会边生成边显示出来——它怎么思考、查了什么、写了什么，你都看得见，而不是对着转圈的加载图标干等。问题大一点，它就把这当成一项研究任务来做，最后交给你一份写好的报告，随时可以回来翻看。

它和普通聊天窗口不一样的地方有两点：

- **它记得住。** 明天再来、甚至把整个服务重启，它依然知道你们之前在做什么。就算你把它的快缓存整个清空，它也会悄悄去永久存储里把细节找回来，接着往下聊，像什么都没发生过。
- **它不会丢进度。** 网络中途断了，重连之后它先把错过的内容一股脑补给你，再继续实时输出。

习惯用终端？同一个引擎也能当全屏终端应用跑：`engram`。

<sub><b>一句话说清原理。</b> 助手是一个用 LangGraph 构建的 ReAct agent，外面套了一层 FastAPI Web 服务。记忆存在两个地方：一个"快缓存"（Redis），旧内容会按设定自然过期；一个"永久存储"（Postgres），什么都不会丢。读取时先看快缓存，没有就去永久存储里找，顺便把结果悄悄放回缓存。长对话会触发后台任务，把对话提炼成记忆——这个后台任务本身也经得起崩溃重启。整个项目带 2,764 个自动化测试。</sub>

## 用来做什么

- **边问边看** —— 实时流式对话：推理过程、工具调用、答案文本都即时出现
- **深度研究出报告** —— 提一个问题，得到流式输出的报告，并自动保存、随时回看
- **跨会话、跨重启的陪伴** —— 会话、记忆、报告都经得起重启
- **一个可以读懂的例子** —— 如果你也在搭 agent 服务，这是一个小而完整、测试充分的项目：流式输出、可靠状态、双层记忆是怎么捏到一起的，没有藏着掖着的魔法
- **终端党的选项** —— 完整的 TUI 和 CLI

## 演示

**它记得住。** 把整个快缓存清空来验证：对话依然接得上。

```bash
# 模拟"近期全忘光了"
docker compose exec redis redis-cli FLUSHDB

# 接着聊——它会去永久存储里把细节找回来
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "上次研究到哪了？"}'

event: answer
data: {"type": "answer", "content": "上次已确认用 Last-Event-ID 方案；缓冲是每会话一个环形…"}
# ↑ 这条回答来自永久存储，答完又自动放回了快缓存
```

**它会流式输出——而且断了也不怕。** 提交研究问题；连接中途断开时，用最后收到的事件编号重连，错过的部分先补发给你：

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking / answer / tool_start / tool_end / done

# 在第 5 个事件处断了？带上最后的事件编号重连：
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# 错过的 6、7… 会先到，然后继续实时输出
```

<!-- IMAGE SLOT: 演示截图或短 asciinema 录屏（在此插入） -->

想一步一步照着走？完整走查脚本：[docs/demo.md](docs/demo.md)

## 安装

你需要：

- Python **3.12+**
- 一个 LLM API key —— 默认 `DEEPSEEK_API_KEY`，任何 OpenAI 兼容服务都行
- Docker —— 只有"一条命令起全栈"才需要

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows；Linux/macOS 用：source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # 填入 DEEPSEEK_API_KEY=sk-...
```

## 快速开始

启动服务：

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000
```

另开一个终端，创建会话、说句话：

```bash
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "主流方案是怎么处理 SSE 断线重连的？"}'
```

事件会一条一条地到：

```text
event: thinking   …   <- 它正在思考
event: answer     …   <- 答案文本，逐字流出
event: tool_start …   <- 它开始搜索或调用工具
event: done           <- 结束
```

浏览器打开 **http://localhost:8000/docs**，所有接口都能当场试。研究跑完后：

```bash
curl -s localhost:8000/sessions/$SID/runs       # 历史运行
curl -s localhost:8000/runs/<run_id>/report     # 写好的报告
```

只想用终端？直接运行 `engram`。

## Docker 支持

```bash
cp .env.example .env      # 填入你的 API key
docker compose up -d
```

| 会启动什么 | 用大白话说 | 在哪 |
|---|---|---|
| **gateway** | Web API —— 会话、实时对话、研究、报告、在线接口调试 | http://localhost:8000 |
| **postgres** | 永久记忆、会话状态、运行历史 | localhost:5432 |
| **redis** | 快缓存 + 后台任务队列 | localhost:6379 |
| **consolidation-worker** | 在后台把旧对话整理成记忆 | — |
| **agent** | 终端应用，按需启动 | — |

- 一切都已接好线——你只需要提供 API key。
- 你的数据在 `.engram/`（日志、产物、数据库与缓存卷）和 `skills/` 里。
- 在 Docker 里用终端应用：`docker compose run --rm agent`
- 想让工具调用跑在 Docker 容器里隔离？按 `docker-compose.yml` 里的注释取消 `docker.sock` 挂载并设置 `ENGRAM_SANDBOX_USE`。

更多：[使用指南](resource/USAGE.zh-CN.md) · [完整走查](docs/demo.md) · [设计笔记](docs/interview-notes.md)

---

## 许可证

[MIT](LICENSE) © Engram Authors

---

<div align="center">

<sub>为关心 agent 是怎么造出来的人而建。</sub>

</div>
