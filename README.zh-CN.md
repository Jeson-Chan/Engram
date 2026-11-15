<a name="readme-top"></a>

<!-- IMAGE SLOT: 居中 Logo / 字标 —— 在此插入，宽度约 45%（如 docs/assets/logo.png） -->

<p align="center">
    <a href="resource/USAGE.zh-CN.md" target="_blank">
        <img src="https://img.shields.io/badge/docs-view-blue?logo=readthedocs&logoColor=white" alt="文档" />
    </a>
    <a href="docs/demo.md" target="_blank">
        <img src="https://img.shields.io/badge/demo-walkthrough-blue" alt="演示" />
    </a>
    <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" />
    <img src="https://img.shields.io/badge/FastAPI-web%20service-blue?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Redis-hot%20cache-blue?logo=redis&logoColor=white" alt="Redis" />
    <img src="https://img.shields.io/badge/Postgres-memory-blue?logo=postgresql&logoColor=white" alt="Postgres" />
    <a href="LICENSE" target="_blank">
        <img src="https://img.shields.io/static/v1?label=license&message=MIT&color=blue" alt="许可证" />
    </a>
</p>

<p align="center">
  <a href="./README.md">English</a> | <b>简体中文</b> | <a href="./README.ja.md">日本語</a>
</p>

# Engram - 一个会记住你的研究助手

> “聊天窗口在你关掉标签页的那一刻就把你忘了。我想要的是一个记得住来龙去脉的研究伙伴——跨天、跨重启、跨网络中断。”

**Engram** 是一个跑在你自己机器上的 AI 研究助手，以一个小型、自托管的 Web 服务形式提供。

创建一个会话、问一个问题，答案会边生成边实时显示——它怎么思考、查了什么、写了什么，你都看得见。问题大一点，它就把这当成一项深度研究任务来做，最后交给你一份写好的报告，随时可以回来翻看。

它和普通聊天窗口不一样的地方有两点：它**记得住**——跨会话、跨重启，就算快缓存被清空也不丢；它**不会丢进度**——网络断了，重连之后先把你错过的部分补给你。

> [!TIP]
> 一条命令启动完整服务：
> ```
> docker compose up -d
> ```

<!-- IMAGE SLOT: 主截图 —— 对话正在流式输出回答（在此插入） -->

---

## Engram 的工作原理

Engram 把一个研究 agent 包进了一个小型 Web 服务。agent 负责思考、搜索、写作；服务把这一切变成浏览器或终端能实时跟上的数据流，并确保这些工作经得起重启和断线。

最值得说的是记忆。它分两层：一个"快缓存"（Redis），旧内容会按设定自然过期；一个"永久存储"（Postgres），什么都不会丢。读取时先看快缓存，没有就去永久存储里找，顺便悄悄把结果放回缓存。把缓存整个清空——助手只是重新查一下需要的东西，然后若无其事地继续。

长对话会由后台任务提炼成记忆。这个任务本身是一条持久队列，同样经得起崩溃和重启，也可以单独跑成 worker 进程。

<!-- IMAGE SLOT: 架构图（在此插入） -->

---

## ⭐ 功能特性

- **🔍 实时流式对话：** 推理过程、工具调用、答案文本都即时出现——没有转圈等待，也不用等整段回复生成完。
- **🔬 深度研究：** 一个问题变成一份流式输出的研究报告，自动保存并列进历史，随时回看。
- **🧠 经得起重启的记忆：** 会话、记忆、历史跨重启保留；热缓存被清空也能从永久存储找回，并在召回时重新加热。
- **🔌 断线安全的流：** 连接断开后，带上最后的事件编号重连，错过的事件先补发，然后继续实时输出。
- **💻 安全沙箱（可选）：** 工具调用跑在 Docker 容器里，带路径约束，agent 写下的文件真正落盘。
- **🖥️ 终端原生：** 同一个引擎也能当全屏 TUI 或滚动式 CLI 跑。
- **🧩 可读、有测试的核：** 小而聚焦、可注入替换的代码库——2,764 个自动化测试；恢复与重放相关的套件在 CI 里对真实 Redis 和 Postgres 实跑。

Engram 默认支持 DeepSeek，也兼容任何 OpenAI 兼容的提供商。

更多内容请参阅[文档](resource/USAGE.zh-CN.md)。

---

## 🧠 记忆与你的数据

一切都在你自己的环境里运行——没有云端往返，没有第三方替你索引对话。

- **快缓存**（Redis）的设计目标就是遗忘：热记忆不再被想起就会过期。
- **永久存储**（Postgres）是事实来源：不会因为变冷而被删除。
- 数据在 `.engram/`（日志、产物、数据库与缓存卷）和 `skills/` 里——备份、迁移、删除都随你。
- 模型提供商由你选择；用本地模型的话，连推理也在你自己的机器上。

---

## 🧭 随时随地使用 Engram

- **Web API** —— FastAPI 服务：会话、流式对话、研究、运行历史与报告。
- **在线接口调试** —— 打开 `/docs`，所有接口都能在浏览器里当场试。
- **终端** —— 全屏 TUI 交互研究，或朴素滚动式 CLI。
- **CLI 单次运行** —— `engram run "问题"`，打印报告后退出。
- **Docker** —— 一条 `docker compose up -d` 起网关、数据库和后台 worker。

---

## 🎬 演示

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

**它会流式输出——而且断了也不怕。**

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

---

## 📦 安装

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

## ⚡ 快速开始

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

## 🐳 Docker 支持

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

---

## 📚 许可证

[MIT](LICENSE) © Engram Authors

<sub>[回到顶部](#readme-top)</sub>
