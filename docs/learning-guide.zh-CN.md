# Engram 项目学习文档

> **一个会记住你的研究助手——网络断了也不丢进度。**
>
> 面向第一次接触 Engram 的读者。读完你应该能回答：Engram 是什么、一条请求怎么走完整个系统、记忆/流式/状态/工具/多 Agent 各自解决什么问题，以及每个设计为什么不是另一种做法。
>
> 基于 `main` 分支（2026-11-15，27 个 commit）整理。本文只描述当前代码里真实存在的行为；设计意图与未完成项会显式标出。

---

## 目录

- 0. 这份文档怎么读
- 1. 项目名片
- 2. 前置概念
- 3. 全局总览
- 4. 模块 01 — Agent 装配与主循环
- 5. 模块 02 — 上下文工程
- 6. 模块 03 — 双层记忆与检索
- 7. 模块 04 — 巩固队列与后台 Worker
- 8. 模块 05 — 会话状态、Checkpoint 与运行工件
- 9. 模块 06 — SSE 流式与断线续传
- 10. 模块 07 — 工具、沙箱与 MCP 安全边界
- 11. 模块 08 — 多 Agent、Skill 与自进化
- 12. 模块 09 — 测试与评测体系
- 13. 当前边界与演进方向
- 14. 面试表达
- 15. 附录

---

## 0. 这份文档怎么读

### 0.1 读者合同

**适合谁**

- 会 Python，能跑 `pip` / `pytest` / `curl`；
- 了解 LLM 基本调用，但没做过完整 Agent 服务；
- 想通过一个真实项目理解「流式输出 + 持久状态 + 双层记忆 + 工具治理」是怎么拼起来的。

**读完你应该能回答**

1. Engram 是什么，不是什么？
2. 一条用户消息从 `POST /sessions/{id}/chat` 进来后，经过哪些层、最后怎么回到 SSE？
3. 为什么记忆要分 Redis 热层和 Postgres 冷层？为什么写路径冷层先落？
4. 为什么巩固队列用 Redis Stream，而不是 pub/sub 或 list？
5. 为什么 LangGraph 会话状态要落 Postgres checkpointer？
6. SSE 断线续传和 Redis Stream 的 pending 重放，为什么是同一套语义？
7. 工具、沙箱、MCP 的边界分别在哪？本地沙箱为什么不是隔离？
8. 多 Agent、Skill、自进化分别解决什么问题，哪些默认关闭？
9. 2,764 个测试证明了什么，又不证明什么？
10. 如果面试官继续追问，每一层能往哪个方向展开？

**本文不覆盖**

- 不逐个讲 584 个 Python 文件；只讲撑起系统骨架的核心路径。
- 不把每个配置项列全；环境变量以 `.env.example` / `USAGE.md` 为准。
- 不评价模型效果；本文关注的是 harness / runtime / 状态 / 边界。
- 不把“设计目标”写成“已完成能力”。当前未完成或默认关闭的部分，会在各章「边界」里写明。

### 0.2 三条阅读路径

| 路径 | 适合场景 | 顺序 |
|---|---|---|
| **15 分钟速览** | 只想先建立系统感 | 本文第 3 章「全局总览」→ `bootstrap.py` → `leader/factory.py` → `gateway/chat.py` → `services/stream_service.py` |
| **完整学习** | 第一次系统学这个项目 | 0 → 1 → 2 → 3 → 01–09 章 → 边界 → 面试表达 |
| **复习** | 面试前快速回看 | 3.2 一条请求 → 3.3 关键文件地图 → 各章「一句话问题 / 边界 / 30 秒讲法」 |

### 0.3 每章强制输出三件事

参考文档的学习方法同样适用于 Engram。每读完一章，合上文档，用自己的话写：

1. **这个模块解决什么问题？**
2. **它是怎么做的？**
3. **为什么这样做，而不是另一种做法？**

写不出来，说明还没吃透；回到该章的「代码落点」和「怎么验证」再读一遍。

---

## 1. 项目名片

### 1.1 一句话

Engram 是一个跑在本地的 AI 研究助手：以 FastAPI Web 服务的形式提供会话、流式对话、深度研究和报告回看；底层是一个用 LangGraph 构建的 ReAct Agent，外面套了一层负责上下文治理、记忆、工具治理、状态持久化和审计的 harness。

它和普通聊天窗口的区别只有两点，但这两点决定了整个架构：

- **它记得住**：会话、记忆、报告跨重启保留；热缓存被清空后，仍能从冷层召回。
- **它不丢进度**：流式连接断了，重连后先补发缺口，再继续实时输出。

### 1.2 它解决的四类问题

| 问题 | 用户感受 | Engram 的解法 | 主要章节 |
|---|---|---|---|
| 跨会话遗忘 | 明天回来， agent 不记得昨天聊到哪 | Redis 热层 + Postgres 冷层 + BM25 召回 + 巩固 worker | 03 / 04 |
| 长对话上下文膨胀 | 聊久了 prompt 越来越长、越来越偏 | 预算阈值 + P1 外化 + P4 摘要 + P5 收尾 | 02 |
| 服务重启/多 worker 状态丢失 | 重启后会话接不上 | LangGraph `AsyncPostgresSaver` + run artifacts | 05 |
| 流式断线 | 网络一抖，答案从头再来 | SSE `id:` + `Last-Event-ID` + per-session 环形缓冲 | 06 |

另外还有两条“工程护栏”：

- **工具治理**：工具注册、沙箱组合、路径白名单、MCP 描述扫描、凭证脱敏（07）；
- **可扩展性**：多 Agent specialist、Skill 注入、自进化/评测层（08，默认多数关闭）。

### 1.3 技术栈

- Python 3.12+
- LangGraph / LangChain `create_agent` + `AgentMiddleware`
- FastAPI + Uvicorn（网关）
- Redis（热层记忆 + Stream 巩固队列）
- Postgres（冷层记忆 + LangGraph checkpointer + run 历史）
- Textual（TUI）、Rich、prompt_toolkit（CLI）
- pytest（2,764 passed / 12 skipped，本地实测 90.20s）
- Docker Compose（gateway / postgres / redis / consolidation-worker / agent）

### 1.4 它不是什么

主动划边界，能避免初学者建立错误预期：

- **不是向量记忆系统**：默认检索是 BM25，不是 embedding；`vector_store` / `graph_store` 是可选叠加，不是默认路径。
- **不是多租户 SaaS**：`SessionRegistry` 目前是进程内内存实现，没有鉴权、配额、租户隔离。
- **不是完整沙箱平台**：Local sandbox 是宿主进程执行 + 规则校验，不是 OS 级隔离；Docker sandbox 才是容器隔离。
- **不是“所有功能默认全开”**：`.env.example` 里 memory、skill、MCP、sandbox 默认关闭；Docker Compose 的全栈路径才会打开记忆与 PG/Redis。
- **不是 Claude Code 的替代品**：它是研究助手 + 可委派 specialist 的架构样例，不是通用 coding CLI。

---

## 2. 前置概念

| 术语 | 在 Engram 里的含义 | 易混点 |
|---|---|---|
| **Agent** | 模型 + 工具 + 记忆 + 环境反馈的循环系统 | 不等于一次 LLM 调用 |
| **Harness** | 包在 Agent 外面的运行时：上下文、工具、状态、恢复、审计、评测 | 不是模型本身 |
| **LangGraph graph** | `create_agent(...)` 编译出的状态图；负责 ReAct 循环与 checkpointer | 不是 Engram 手写的 `while` 循环 |
| **Middleware** | LangChain `AgentMiddleware` 的 hook：`before_model` / `after_model` / `wrap_tool_call` / `after_agent` 等 | 不是 HTTP 中间件 |
| **Thread** | LangGraph 状态隔离键；一个会话一个 `thread_id` | 不等于 Python 线程 |
| **Session** | 网关层的会话入口；`session_id → thread_id` | 目前只存在内存 |
| **Run** | 一次 `ask` / chat / research 请求对应的独立执行记录 | 不等于整个 session |
| **Checkpoint** | LangGraph 在每一步保存的图状态；PG 持久化后可跨重启恢复 | 不等于 Redis 记忆 |
| **Hot tier** | Redis 记忆层：分区键 + TTL，读命中续命 | 会被淘汰 |
| **Cold tier** | Postgres 记忆层：全量 JSONB 沉淀 | 不淘汰，是兜底真相 |
| **Consolidation** | 把多轮对话抽取成记忆、再把多条 episodic 合并成 semantic | 异步、at-least-once |
| **SSE** | Server-Sent Events；每帧带 `id:`，客户端重连带 `Last-Event-ID` | 不是 WebSocket |
| **MCP** | Model Context Protocol；外部工具服务器 | 工具描述也可能被注入 |
| **Skill** | 提示词层面的“研究过程知识”，不是可执行函数 | 与 MCP tool 职责不同 |
| **Specialist** | 外部 CLI Agent（pi / codex / claude）或内部 subagent | 黑盒，自带模型与循环 |

---

## 3. 全局总览

### 3.1 三个面

Engram 的模块很多，但可以先压成三个面：

| 面 | 决定什么 | 主要模块 |
|---|---|---|
| **控制面** | 请求怎么被装配、推进、停止 | `app/bootstrap.py`、`leader/factory.py`、`leader/agent.py`、`app/gateway/chat.py`、`app/services/stream_service.py` |
| **状态面** | 记住什么、恢复什么、审计什么 | `context_engineering/`、`memory/`、`runtime/`、`journal/` |
| **证据面** | 怎么验证、怎么回看、怎么比较 | `tests/`、`run artifacts`、`PGRunStore`、`journal events`、`multiagent/metrics` |

初学者最常见的误区，是把这三个面混成一团：看到 `memory.py` 就以为它负责“记住聊天记录”，看到 `checkpointer.py` 就以为它负责“恢复记忆”。实际上：

- **checkpointer** 保存的是 LangGraph 的图状态，服务于“同一 thread 继续跑”；
- **memory** 保存的是跨轮/跨会话的事实，服务于“少重复读、少重复确认”；
- **run artifacts / journal** 保存的是“这次到底发生了什么”，服务于回放和审计。

### 3.2 一条请求怎么跑完整个 Engram

以 `POST /sessions/{session_id}/chat` 为例：

```text
Client
  │  POST /sessions/{id}/chat  {"message": "..."}
  ▼
FastAPI gateway (chat.py)
  │  1. SessionRegistry.get(session_id) → thread_id
  │  2. RunManager.create_run(...) → run_id + output_dir + RunJournal
  │  3. mark_running
  ▼
EngramStreamClient (stream_service.py)
  │  graph.astream(state, config, stream_mode=["values","messages","custom"])
  ▼
LangGraph graph (create_agent)
  │  before_model hooks:
  │    TaggedContext / MessageNormalizer / Strategy(P1-P5)
  │    SystemContext / SkillInjection / MemoryRecall / ToolCall ...
  │  model_call
  │  after_model hooks:
  │    budget track / tool ledger / stall detection / todo / reflection
  │  tool_call → builtin / MCP / sandbox
  │  after_agent hooks:
  │    report / title / skill metrics
  ▼
StreamEvent 序列
  │  thinking / answer / tool_start / tool_end / budget_update / done
  ▼
SSE frames
  │  id: N
  │  event: answer
  │  data: {...}
  ▼
Client
```

同时发生的“旁路”：

- **checkpointer** 在 LangGraph 每一步保存状态；配了 `ENGRAM_CHECKPOINT_DSN` 时是 `AsyncPostgresSaver`，否则 `InMemorySaver`。
- **RunJournal** 把 `agent.started` / `llm.request` / `tool.called` / `run.finished` 等事件追加到 `events.jsonl`。
- **PGRunStore** 在 run 状态转移点把记录 upsert 到 `runs` 表；`report_path` 指向最终报告产物。
- **SSE buffer** 把每帧塞进 per-session 环形缓冲，供 `Last-Event-ID` 重连补齐。

### 3.3 关键文件地图

| 文件 | 角色 | 为什么先看它 |
|---|---|---|
| `engram/backend/app/bootstrap.py` | 启动装配 | 一次看清 config、模型路由、MCP、sandbox、skill、multiagent、memory、registry、leader agent 怎么装起来 |
| `engram/backend/agents/leader/factory.py` | Graph 工厂 | `make_lead_agent()` + `_build_middlewares()`；中间件顺序在这里 |
| `engram/backend/agents/leader/agent.py` | 薄壳 | `LeaderAgent.run()` 只做 `graph.ainvoke` + reporter + artifact |
| `engram/backend/agents/state/types.py` | 状态 schema | `ThreadState` 字段与 reducer，决定哪些状态会被合并/去重 |
| `engram/backend/app/gateway/chat.py` | SSE 对话端点 | 网关如何绕过同步入口、如何补发缺口、如何落 run |
| `engram/backend/app/services/stream_service.py` | 流式标准化 | `graph.astream` → `StreamEvent`；去重、内部 LLM 过滤、selector 泄漏处理 |
| `engram/backend/agents/context_engineering/strategies/default/strategy.py` | 上下文治理 | P1–P5 阈值、外化、摘要、收尾 |
| `engram/backend/agents/memory/adapters/tiered_store.py` | 双层记忆 | 冷先写、热先读、冷命中回填 |
| `engram/backend/agents/memory/stream_queue.py` | 巩固队列 | XADD / XREADGROUP / XACK / XAUTOCLAIM |
| `engram/backend/agents/runtime/pg_checkpointer.py` | 持久 checkpointer | `AsyncPostgresSaver` + 连接池 |
| `engram/backend/agents/runtime/run_manager.py` | 运行记录 | run 生命周期与 `record.json` / `events.jsonl` |
| `engram/backend/app/gateway/sse_buffer.py` | 断线续传 | 环形缓冲 + `Last-Event-ID` |
| `engram/backend/agents/sandbox/sandbox.py` | 沙箱编排 | `validate → translate → execute → mask` |
| `engram/backend/agents/mcp/loader.py` | MCP 生命周期 | 并行加载、guard 顺序、失败隔离 |
| `engram/backend/tests/v1/unit/` | 测试锚点 | 关键行为都有对应测试文件 |

### 3.4 15 分钟路径

如果只剩 15 分钟，按这个顺序看：

1. `app/bootstrap.py` 的 `bootstrap_runtime()`：看对象图怎么装。
2. `leader/factory.py` 的 `make_lead_agent()` 和 `_build_middlewares()`：看中间件顺序。
3. `app/gateway/chat.py`：看一条请求怎么从 HTTP 进入 graph。
4. `app/services/stream_service.py`：看 graph 输出怎么变成 SSE 事件。

### 3.5 10 分钟复习

1. 先回忆三个面：控制面 / 状态面 / 证据面。
2. 再回忆一条请求：session → run → graph → middleware → model/tool → SSE → artifacts。
3. 然后回忆三个关键分工：checkpointer（图状态）/ memory（跨轮事实）/ run artifacts（过程证据）。
4. 最后回忆三条“为什么”：为什么冷先写、为什么用 Stream、为什么 SSE 缓冲与 PEL 同构。

---

## 4. 模块 01 — Agent 装配与主循环

### 4.1 一句话问题

> 一句用户请求，怎么被装配成一个有中间件、有工具、有状态、能停止的 Agent 执行？

### 4.2 背景

很多 Agent demo 是手写 `while True`：调模型、解析工具、执行、拼历史。这样写能跑，但一旦要加“上下文压缩、记忆召回、工具账本、权限、审计、报告”，主循环会迅速变成一团 `if`。Engram 的选择是：

- 用 LangGraph `create_agent` 编译 ReAct graph；
- 把横切能力全部做成 `AgentMiddleware`；
- `LeaderAgent` 只做薄壳：`graph.ainvoke` + reporter + artifact。

### 4.3 装配流程

`bootstrap_runtime()` 的顺序（简化）：

1. 加载 `AppConfig`，锚定相对路径到项目根；
2. 创建 thread 目录与 `thread-events.jsonl`；
3. `ModelRouter` 构造 researcher / reporter 模型（按角色路由链，deepseek 兜底）；
4. 加载 builtin 工具（web_search / browse_page / read_snapshot / skill_search）；
5. 加载 MCP（`McpManager`，并行连接、熔断、fallback）；
6. 加载 sandbox provider（`ENGRAM_SANDBOX_USE` 非空才启用）；
7. 加载 Skill（`ENGRAM_SKILL_ENABLED=true` 才启用）；
8. 装配 multiagent（specialist + subagent + metrics + orchestration）；
9. 装配 memory（`ENGRAM_MEMORY_USE=default` 才启用）；
10. `CapabilityRegistry` 收口模型/工具/reporter/artifact/sandbox/skill/specialist/memory；
11. `make_lead_agent(...)` 编译 graph；
12. 返回 `AppRuntime`。

**关键点**：这些“重活”只在启动时做一次，请求路径不重建。`runtime_factory` 可注入，测试传 stub，避免真实 provider/网络。

### 4.4 中间件顺序

`_build_middlewares()` 的顺序是有语义的，不是随便排：

| 顺序 | 中间件 | 作用 |
|---|---|---|
| 1 | `TaggedContextMiddleware` | 把上下文渲染成标签块 + `<turn>` 时间戳，request-scoped |
| 2 | `MessageNormalizerMiddleware` | 合并/规范 SystemMessage，兼容 strict backend |
| 3 | `StrategyMiddleware` | 上下文治理策略 bundle（`DefaultStrategy` 的 6 个 hook） |
| 4 | `SystemContextMiddleware` | 注入 system context 元数据 |
| 5 | `SkillInjectionMiddleware` | `before_model` 注入 active skills |
| 6 | `SkillMetricsMiddleware` | `wrap_tool_call` 标记 applied；`after_agent` 归因 |
| 7 | `SkillActivationMiddleware` | `before_model` 关键词建议 skill |
| 8 | `TitleMiddleware` | `after_agent` 生成会话标题 |
| 9 | `RunJournalMiddleware` | 记录 agent/model/tool 生命周期事件 |
| 10 | MCP Audit（条件） | MCP 调用审计 |
| 11 | `SandboxMiddleware`（条件） | 注入 sandbox_id / 恢复 ContextVar |
| 12 | `MemoryMiddleware` | `before_model` 召回注入 |
| 13 | `MemoryConsolidationMiddleware` | 每 N 轮提交巩固任务 |
| 14 | `HelpRequestMiddleware` | 拦截 `ask_help`，暂停 graph |
| 15 | `DanglingToolCallMiddleware` | 修补中断后悬空的 tool_calls，防 400 |
| 16 | `ToolCallMiddleware` | 工具账本、失败分类、重试/硬预算 |
| 17 | Orchestration（条件） | 多 Agent 编排 |
| 18 | `EvidenceMiddleware` | 把工具结果写入 observations/sources/errors |
| 19 | `StallDetectionMiddleware` | 检测死局，暂停/强制收尾 |
| 20 | `TodoMiddleware` | 待办完成度约束（expert 模式强制） |
| 21 | `ReflectionMiddleware` | 退出前反思（expert 模式更激进） |
| 22 | `ReportMiddleware` | `after_agent` 合成 `final_report` |

> 说明：`LoopDetectionMiddleware` 在代码里仍存在，但 `_build_middlewares()` 已注释掉（用户要求取消循环上限约束）。不要把“文件存在”当成“已挂载”。

**顺序为什么重要**

- 记忆在 Sandbox 之后、ToolCall 之前：记忆可以引用 sandbox 结果，但注入的 `HumanMessage` 不能插进 tool pairing；
- ToolCall 在最外层 `wrap_tool_call`：能看到所有工具最终结果和内层异常；
- `DanglingToolCallMiddleware` 在 `before_model` 修补 `AIMessage(tool_calls)` 缺失的 `ToolMessage`，否则下一轮 LLM 会 400；
- `ReportMiddleware` 在 `after_agent`，必须在工具和反思之后。

### 4.5 代码落点

```python
# engram/backend/agents/leader/factory.py
return LeaderAgent(
    graph=create_agent(
        model=model,
        tools=tools or None,
        middleware=_build_middlewares(...),
        system_prompt=apply_prompt_template(...),
        state_schema=ThreadState,
        checkpointer=get_checkpointer(),
    ),
    capability_registry=registry,
)
```

```python
# engram/backend/agents/leader/agent.py
final_state = asyncio.run(self.graph.ainvoke(
    {"messages": [HumanMessage(content=question)], ...},
    config=config,
))
```

**注意**：`LeaderAgent.run()` 内部是 `asyncio.run(...)`。在有事件循环的 ASGI worker 里再嵌套 `asyncio.run` 会抛 `RuntimeError`。所以网关**绝不走** `LeaderAgent.run`，而是直接包装 `graph.astream`（见第 9 章 / 06 章）。这不是“性能优化”，而是“根本跑不起来”。

### 4.6 关键设计与反方案

**为什么用 `create_agent` + middleware，而不是手写主循环？**

- ReAct 循环、工具节点、checkpointer、消息 reducer 都是 LangGraph 已经验证过的；
- 横切能力做成 middleware，可单独测试、可条件挂载、顺序可读；
- `LeaderAgent` 保持薄壳，业务逻辑不往类里堆。

**为什么 default / expert 两套参数？**

- `expert_mode=False`：工具只加载 core，Todo 不强制完成，Reflection 不 jump，Report 不自动合成；
- `expert_mode=True`：加载 core+deferred，Todo 强制，Reflection 用 `SufficiencyStrategy`，Report 自动合成。
- 目的：同一套 graph，用参数控制“轻聊天”与“深度研究”的行为差异，不维护两份代码。

**为什么状态用 `ThreadState` 而不是随便一个 dict？**

- `ThreadState` 继承 `AgentState`，保留 `messages` 的 `add_messages` reducer；
- `observations` / `sources` / `errors` / `artifacts` 等字段有各自的 reducer（去重、限长、按 id 合并）；
- 状态 schema 明确后，checkpointer 才能稳定序列化/恢复。

### 4.7 Trade-off

- **减少**：手写循环的分支、重复的工具调度、每加一个能力就改主循环。
- **换来**：中间件链的复杂度、顺序敏感性、LangGraph 语义的学习成本。
- **代价**：主循环不再是“一眼看到底”的 100 行；调试要理解 hook 时机与 `Command(goto=...)`。

### 4.8 边界

- `LeaderAgent.run()` 只适合非流式 CLI；网关必须用 `EngramStreamClient`。
- 中间件数量多，顺序变化可能破坏 pairing / 记忆注入 / 报告时机。
- `LoopDetectionMiddleware` 当前未挂载；“没有循环上限”是当前行为，不是遗漏。
- `Skill` / `MCP` / `Sandbox` / `Memory` / `MultiAgent` 都是条件挂载；看代码时先确认配置是否启用。

### 4.9 怎么验证

- `engram/backend/tests/v1/unit/leader/test_make_lead_agent.py`
- `engram/backend/tests/v1/unit/middlewares/test_agent_middlewares.py`
- `engram/backend/tests/v1/unit/middlewares/test_middleware_params.py`
- `engram/backend/tests/v1/integration/test_minimum_agent_loop.py`
- `engram/backend/tests/v1/integration/test_default_strategy_e2e.py`

### 4.10 面试 30 秒

> Engram 的 Agent 层是一个 LangGraph `create_agent` 编译出来的 ReAct graph，外面用 `AgentMiddleware` 挂了上下文治理、记忆召回、工具账本、沙箱、报告等横切能力。`LeaderAgent` 只是薄壳，负责 `graph.ainvoke` 和落报告；真正的主循环在 graph 里。网关不走这个同步入口，而是直接用 `graph.astream` 做流式，因为 `LeaderAgent.run` 内部的 `asyncio.run` 在 ASGI 事件循环里会直接报错。

### 4.11 小结

这一章的重点不是“中间件有哪些”，而是“为什么主循环要交给 graph、横切能力为什么要做成中间件、薄壳和流式入口为什么要分开”。

---

## 5. 模块 02 — 上下文工程

### 5.1 一句话问题

> 长对话里，怎么让模型每一轮看到“够用、稳定、不过载”的上下文，而不是把整段历史越堆越长？

### 5.2 背景

研究任务会不断产生：用户消息、模型回复、工具输出、文件内容、shell 日志、记忆召回。它们都可能有价值，但寿命不同：

- **当前请求**：必须完整保留；
- **最近几轮**：下一步最依赖；
- **旧工具输出**：可能有用，但不该每轮都带全文；
- **稳定系统规则**：每轮都要，但不应重复膨胀。

粗暴截断的问题不是“简单”，而是“不知道自己切掉了什么”。一旦把 `AIMessage(tool_calls)` 和对应的 `ToolMessage` 切散，下一轮 LLM 直接 400。Engram 的上下文治理因此做成**分层 + 阈值 + 可外化 + 可摘要**。

### 5.3 设计：P1–P5 分段

`DefaultStrategy` 用当前 token 占模型窗口的比例 `fraction` 触发不同阶段：

| 阈值 | 阶段 | 动作 | 目的 |
|---|---|---|---|
| `0.40` | P1 | 外化旧工具输出到磁盘，保留 preview + path | 把大块历史移出 prompt |
| `0.50` | P2 | 预留（`track()` 会把 P2 写入 `pending`，但 `before_model` 没有对应处理） | 未来做 thinking/推理压缩 |
| `0.60` | P3 | 阈值和分支存在，但 `track()` 当前不把 P3 写入 `pending`，因此实际不会触发 | 未来做 observations top-N |
| `0.80` | P4 | 全量摘要：保留最近 6 条，旧消息合并成 summary | 大幅收缩 |
| `0.90` | P5 | 剥掉最后一条 AI 的 `tool_calls`，注入收尾提示，`jump_to="model"` | 强制模型收尾，不再调工具 |
| `0.99` | hard stop | 99% 硬底线提示 | 最后保险 |

`fraction` 通过 `BudgetTrackerExecutor.track()` 计算：

- 用 `AIMessage.usage_metadata` 的 input/output token 增量累计；
- 用 `token_counter(messages)` 估算当前上下文；
- 窗口大小由 `resolve_window_size(model)` 解析：模型属性 → `_identifying_params` → 模型名前缀映射 → 默认 128,000。

### 5.4 四个执行器

| 执行器 | 文件 | 做什么 |
|---|---|---|
| `BudgetTrackerExecutor` | `strategies/default/budget.py` | 初始化/累计预算、算 `fraction`、标 `pending`、清理 run 状态 |
| `ExternalizerExecutor` | `strategies/default/externalizer.py` | 把超阈值工具输出写盘，替换成 preview + 路径 |
| `SummarizerExecutor` | `strategies/default/summarizer.py` | P4 摘要，保留最近 N 条，处理 pairing 边界 |
| `SnapshotExecutor` | `strategies/default/snapshot.py` | P4 前存快照，记录 `snapshot_path` |

**P1 外化的细节**

- 按 `HumanMessage` 分 turn；
- 最近 `exempt_rounds=2` 轮豁免；
- 每轮保留最新 1 个工具结果，其余可外化；
- 单条文本超过 `min_chars=500` 才外化；
- 已外化的消息用 `additional_kwargs` 标记，幂等跳过；
- 写盘成功 → 替换为 `preview + [externalized path=... tokens~...]`；
- 写盘失败 → 保留原文，不影响主流程。

**P4 摘要的细节**

- `preserve_recent=6`；
- 切分点会 `_snap_to_pairing()`：如果切到 `ToolMessage`，回退到配对的 `AIMessage`，防止孤立 tool result；
- `preserved` 里的孤立 ToolMessage / 孤立 AIMessage(tool_calls) 移到待摘要区；
- 摘要前对外化孤立 tool result；
- 用 `RemoveMessage(REMOVE_ALL_MESSAGES)` + summary + preserved 一次性替换；
- 摘要调用带 `tags=["internal_llm"]`，防止泄漏到流式 answer。

**P5 收尾的细节**

- 找到最后一条带 `tool_calls` 的 `AIMessage`；
- 复用原 id，清空 `tool_calls`，同步清 `additional_kwargs.tool_calls/function_call`；
- 注入 `HumanMessage(name="context_budget_stop", hide_from_ui=True)`；
- `jump_to="model"`，跳过 ToolNode，避免孤立 tool_calls；
- `warned=True` 防重复触发死循环。

**Pairing 保护**

`_ensure_pairing()` 在 `before_model` 扫描所有 `AIMessage(tool_calls)`，如果缺对应 `ToolMessage`，补一条 `status="error"` 的占位。这是防止 LLM 400 的硬约束。

### 5.5 代码落点

- `engram/backend/agents/context_engineering/strategies/default/strategy.py`
- `engram/backend/agents/context_engineering/strategies/default/budget.py`
- `engram/backend/agents/context_engineering/strategies/default/externalizer.py`
- `engram/backend/agents/context_engineering/strategies/default/summarizer.py`
- `engram/backend/agents/context_engineering/strategies/default/snapshot.py`
- `engram/backend/agents/context_engineering/utilities.py`（token_counter / resolve_window_size）
- `engram/backend/agents/context_engineering/strategy_middleware.py`（6 hook 路由）

### 5.6 关键设计与反方案

**为什么按阈值分层，而不是每次固定裁多少字符？**

- 不同模型窗口差异很大（8k / 64k / 200k / 1M）；
- 固定字符数在 200k 模型上过度压缩，在 8k 模型上又不够；
- 按窗口比例触发，能把“什么时候该压缩”与模型解耦。

**为什么外化到磁盘，而不是直接删掉？**

- 过程证据还在，可回看；
- prompt 里保留 preview + path，模型知道“有这个东西”；
- 写盘失败可降级为原文，不阻塞主流程。

**为什么摘要要保留最近 6 条？**

- 下一步最依赖最近发生的事；
- 全量摘要会丢“刚刚的工具结果/错误”；
- 保留窗口是一个简单、可解释的近因优先策略。

**为什么 P5 要剥 tool_calls 而不是直接结束？**

- 模型可能在最后一条 AI 消息里已经决定调工具；
- 直接结束会留下未配对的 tool_calls，checkpointer 恢复后下一轮 400；
- 复用 id 清空 tool_calls + jump model，能让模型基于现有证据收尾。

### 5.7 Trade-off

- **减少**：prompt 无限膨胀、全量历史重放、粗暴截断导致的 pairing 断裂。
- **换来**：治理链更复杂、摘要可能丢信息、外化文件需要清理策略。
- **代价**：P4 摘要是一次 LLM 调用，增加延迟与成本；P1 外化增加磁盘 IO。

### 5.8 边界

- **P2/P3 当前都没有实际压缩动作**：`BudgetTracker.track()` 会把 P2 写入 `pending`，但 `before_model` 没有 P2 分支；P3 的阈值和 `before_model` 分支都存在，但 `track()` 不会把 P3 写入 `pending`，所以 P3 实际不会触发。不要把“代码里有分支”当成“运行时会生效”。
- 预算是**整窗比例**，不是 per-section 预算；没有“prefix 多少、history 多少”的独立配额。
- 摘要是 lossy 的；重要事实应在记忆层另行沉淀，而不是只靠摘要。
- 外化文件不会自动回注；模型需要时得通过工具/路径重新读取（取决于 sandbox 可见范围）。
- pairing 保护是防御性的，不是根因修复；真正避免 400 还要保证工具调用/结果成对产生。

### 5.9 怎么验证

- `engram/backend/tests/v1/unit/context_engineering/test_default_strategy.py`
  - `test_budget_track_pending`
  - `test_p5_strips_tool_calls_and_jumps`
  - `test_p99_uses_hard_stop_message`
  - `test_ensure_pairing_supplements_missing_toolmessage`
  - `test_p1_fifo_externalizes_oldest_first`
  - `test_p4` 相关摘要/快照测试
- `engram/backend/tests/v1/unit/context_engineering/test_strategy_middleware.py`
- `engram/backend/tests/v1/unit/context_engineering/test_state_and_utilities.py`

### 5.10 面试 30 秒

> Engram 的上下文治理不是粗暴截断，而是按当前 token 占模型窗口的比例分阶段：40% 开始把旧工具输出外化到磁盘并保留 preview，80% 做摘要并保留最近 6 条，90% 剥掉最后的 tool_calls 并 jump 到 model 强制收尾，99% 硬停。整个过程有 pairing 保护，避免 AIMessage(tool_calls) 和 ToolMessage 被切散导致 400；外化和摘要都会留快照/路径，方便回看。

### 5.11 小结

上下文工程的核心不是“让 prompt 更短”，而是“知道自己在删什么、为什么删、删了以后还能不能回看”。

---

## 6. 模块 03 — 双层记忆与检索

### 6.1 一句话问题

> 多轮/跨会话任务里，哪些事实值得留下来？留下来以后，怎么保证它们还能继续可信？

### 6.2 背景

代码/研究 Agent 经常重复劳动：上一轮刚读过文件，下一轮又读；刚确认过事实，过两轮又忘。把所有历史塞回 prompt 会导致上下文膨胀；只靠摘要又会丢失局部事实。

Engram 的记忆不是“知识库”，而是**工作记忆 + 长期事实**：

- 热层 Redis 管“快与淘汰”；
- 冷层 Postgres 管“全量与兜底”；
- 检索用 BM25 + Ebbinghaus 强度；
- 检索命中会强化记忆（access_count + strength 写回）。

### 6.3 数据模型：MemoryTrace

`MemoryTrace` 是 frozen dataclass，核心字段：

| 字段 | 作用 |
|---|---|
| `id` | `SHA256(content + type)[:16]`，同内容同类型去重 |
| `content` | 记忆文本 |
| `type` | `episodic` / `semantic` / `procedural` |
| `strength` | 当前强度 0~1（lazy decay 计算） |
| `base_strength` | 初始强度（由类型决定） |
| `decay_rate` | 衰减率 |
| `access_count` | 累计访问次数 |
| `last_accessed` | 最后访问时间 |
| `importance` | 语义重要性 |
| `associations` | 关联（扩散激活预留） |
| `source` | 来源（thread / worker） |
| `metadata` | tags / project / forgotten 等 |
| `operation_log` | 操作日志，最多 20 条 FIFO |

三种类型对应不同的默认衰减参数：

- `episodic`：base 0.7 / decay 0.1（事件记忆，衰减快）
- `semantic`：base 0.8 / decay 0.02（提炼知识，衰减慢）
- `procedural`：base 0.9 / decay 0.005（技能，几乎不衰减）

### 6.3.1 四类记忆操作

`DefaultMemoryManager` 提供四个原子操作。核心原则是“工具里无 LLM”：需要 LLM 生成的内容（合并文本、更新文本）由外部传入，manager 只做存储编排。

| 操作 | 入口 | 做什么 | 关键约束 |
|---|---|---|---|
| **Encode** | `manager.encode()` | 创建新记忆 | id = `SHA256(content + type)[:16]`；同内容同类型幂等返回旧 trace |
| **Associate** | `manager.associate()` | 两条记忆双向关联 | 超上限时 LRU 淘汰 strength 最低的关联 |
| **Consolidate** | `manager.consolidate()` | 多条 episodic 合并成一条 semantic | 2~10 条；旧 trace 标记 `forgotten=True`，不物理删除 |
| **Reconsolidate** | `manager.reconsolidate()` | 更新已有记忆内容 | id 不变；保留原 strength；`new_content` 由外部传入 |

每类操作都会 append `OperationLog`（最多 20 条 FIFO），并 emit `memory.*` journal 事件；retrieve 不记 operation_log，因为高频，强化已经体现在 `strength` / `access_count`。

### 6.4 衰减公式

`EbbinghausDecayPolicy.compute_strength()`：

```text
strength = base_strength × (1 - decay_rate)^time_hours
         + log(1 + access_count) × 0.1
         + importance × 0.05
```

- `time_hours` 从 `last_accessed` 算；没有访问过则从 `created_at` 算；
- 结果钳制到 `[0, 1]`；
- **lazy decay**：不在后台定时改所有记忆，只在 retrieve 时计算；
- retrieve 命中后 `with_strength()` 创建新 trace，`store.update()` 写回。

### 6.5 检索：BM25 + 强度

`HybridRetriever` 默认是纯 BM25：

- 构造时从 `store.list_all()` 全量建倒排索引（排除 `metadata.forgotten=True`）；
- tokenizer 默认是 `text.lower().split()`；
- 查询时算 BM25 相似度；
- 过滤 `strength < query.min_strength`；
- 复合分数：`score = similarity × 0.7 + strength × 0.3`；
- 按 score 降序取 `top_k`；
- 命中的 trace 调 `with_strength` + `store.update`（强化写回）。

### 6.6 双层存储：冷先写，热先读

`TieredMemoryStore` 的读写语义：

| 操作 | 行为 |
|---|---|
| `add` | **先写 cold**（持久性保证），再写 hot；hot 冲突则 `update` |
| `get` | **先读 hot**；hot miss 读 cold；cold 命中回填 hot |
| `update` | 先更新 cold，再更新 hot；hot 不存在则 add |
| `batch_update` | 先 cold 批量，再逐条 hot |
| `remove` | 双删 |
| `list_all` | 以 cold 全量为真相；同 id 时 hot 版本胜出（更新） |

**Redis 热层**

- key：`engram:mem:{user}:{thread}:{trace_id}`
- 全局索引：`engram:mem:idx` hash（trace_id → partition）
- 分区 id 集合：`engram:mem:ids:{user}:{thread}`
- 如果设置了 `ENGRAM_MEMORY_TTL_SECONDS`，每条 key 带 TTL；读命中 `expire` 续命——“常被想起的记忆保持热，久不想起的自然冷却”
- **未设置 `ENGRAM_MEMORY_TTL_SECONDS` 时 `_ttl=None`，热层不设置 Redis key TTL**。`RedisMemoryStore` 的 docstring 说默认来自 `forget.ttl_hours`，但当前实现没有把 `MemoryConfig.forget` 接进构造器；以代码为准。
- `MemoryConfig.forget` 的 `ttl_hours` / `strength_threshold` 只用于 `CompositeForgetPolicy.should_forget()`；当前代码里 `should_forget()` 没有调用点，所以它也不负责实际淘汰。
- key 过期后，索引残留会在 `get/list_all` 时 lazy 清理

**Postgres 冷层**

- 表 `memory_traces(trace_id PK, user_id, thread_id, payload JSONB, created_at, updated_at)`
- 与 Redis 共用同一套 `_dump/_load` 序列化器
- 没有 TTL；是热层淘汰后的兜底真相

### 6.7 代码落点

- `engram/backend/agents/memory/schema.py`
- `engram/backend/agents/memory/strategies/default/decay.py`
- `engram/backend/agents/memory/strategies/default/retriever.py`
- `engram/backend/agents/memory/adapters/redis_store.py`
- `engram/backend/agents/memory/adapters/pg_store.py`
- `engram/backend/agents/memory/adapters/tiered_store.py`
- `engram/backend/agents/memory/strategies/default/manager.py`
- `engram/backend/agents/memory/strategies/default/strategy.py`（`build_default_provider`）
- `engram/backend/agents/middlewares/memory_recall_middleware.py`

### 6.8 关键设计与反方案

**为什么不用向量库？**

- 当前体量不需要 embedding 依赖；
- BM25 可解释：为什么召回这条，能说清是关键词命中；
- `vector_store` / `graph_store` 是可选叠加，不是默认；
- 代价：中文分词弱（默认按空格切），语义召回不如向量。

**为什么写路径冷先写？**

- 冷层是持久性保证；热层只是缓存；
- 先写热层再写冷层，如果冷层失败，会出现“热层有、冷层没有”的假持久；
- 先写冷层，热层失败最多是“这次不快”，记忆仍在。

**为什么读路径热先读？**

- 热层是低延迟路径；
- 热 miss 才查冷，冷命中回填热，形成“再次想起 → 重新变热”的语义；
- 热层异常必须 fall through 到冷层，不能因为 Redis 挂了就丢记忆。

**为什么 ID 用内容哈希？**

- 同内容同类型天然去重；
- consolidate 的 merged_content 也可用同 id 幂等；
- 代价：16 位十六进制有碰撞概率（低，但不是零）；内容变化后 id 变化，reconsolidate 需要显式更新。

### 6.9 Trade-off

- **减少**：重复读取、重复确认、热路径延迟、冷层全量查询成本。
- **换来**：双层一致性、TTL 语义、回填逻辑、序列化约束。
- **代价**：BM25 对中文不友好；热层淘汰后首次召回要走冷层；consolidate 旧 trace 只标记 forgotten，不删除，冷层会持续增长。

### 6.10 边界

- 默认 `ENGRAM_MEMORY_USE` 为空 → 记忆禁用；只有配 `default` 或 Docker Compose 才启用。
- 默认 tokenizer 是空格 + 小写，中文记忆召回效果有限；没有 jieba。
- 默认没有 vector/graph；embedding 字段预留但未使用。
- `forgotten` 是软删除，检索过滤；冷层数据不会自动物理清理。
- 记忆抽取与 consolidate 依赖 LLM；抽取失败只 log，不阻塞主流程。
- **热层 TTL 默认未启用**：不设 `ENGRAM_MEMORY_TTL_SECONDS` 时 Redis key 不过期；README 的“热层会自然过期”要在这个前提下理解。`CompositeForgetPolicy.should_forget()` 当前没有调用点，`forget.ttl_hours` 不会自动淘汰记忆。
- 热层 TTL 到期后，索引残留 lazy 清理；极端情况下 `list_all` 可能看到短暂残留。

### 6.11 怎么验证

- `engram/backend/tests/v1/unit/memory/test_tiered_store.py`
  - `test_dual_write_sediments_cold_first`
  - `test_hot_miss_falls_to_cold_and_backfills`
  - `test_hot_failure_falls_through_to_cold`
  - `test_live_flush_hot_recall_from_cold`（需要 Redis/PG，本地无 DSN 时 skip）
- `engram/backend/tests/v1/unit/memory/test_strategies_default.py`
- `engram/backend/tests/v1/unit/memory/test_e2e_recall.py`
- `engram/backend/tests/v1/unit/memory/test_schema.py`
- `engram/backend/tests/v1/unit/memory/test_redis_store.py`

### 6.12 面试 30 秒

> Engram 的记忆分两层：Redis 热层负责低延迟和 TTL 淘汰，Postgres 冷层负责全量兜底。写路径冷先落，保证持久性；读路径热先读，miss 查冷并回填热。检索默认 BM25 + Ebbinghaus 强度，复合分数 0.7 相似度 + 0.3 强度，命中会强化写回。这样热层被清空也不会丢记忆，只是首次召回慢一点。

### 6.13 小结

记忆层的关键不是“存了多少”，而是“写的时候谁先落、读的时候谁兜底、过期了怎么不误信”。

---

## 7. 模块 04 — 巩固队列与后台 Worker

### 7.1 一句话问题

> 记忆抽取和 consolidate 都要调 LLM，怎么做到不阻塞主对话，还能在 worker 崩溃/重启后不丢任务？

### 7.2 背景

`MemoryConsolidationMiddleware` 每 N 轮提交一个任务：把最近 N*2 条消息交给 worker，由 worker 调 LLM 抽取 episodic 记忆，再在候选 ≥ 10 时合并成 semantic。这个过程：

- 会调 LLM，慢；
- 可能失败；
- 不能阻塞用户下一轮对话；
- worker 可能崩溃，任务不能丢。

Engram 因此把“进程内队列”升级为“Redis Stream 消费者组”，并保留无 Redis 时的进程内回退。

### 7.3 生产/消费链路

```text
MemoryConsolidationMiddleware (aafter_model, 每 N 轮)
  │  MemoryTask(thread_id, recent messages, turn_count)
  ▼
MemoryWorker.submit / StreamConsolidationQueue.submit
  │  XADD engram:mem:consolidate {thread_id, turn_count, messages}
  ▼
StreamConsolidationConsumer (web inline 或独立 consolidation-worker 进程)
  │  XREADGROUP GROUP consolidators <consumer> COUNT 10 BLOCK 5000 STREAMS ... >
  │  XAUTOCLAIM 认领孤儿 pending（min-idle 30s）
  ▼
MemoryWorker._process
  │  1. LLM 抽取 JSON → manager.encode
  │  2. 若 episodic 总数 ≥ 10 → 取最旧 10 条 → LLM 合并 → manager.consolidate
  ▼
XACK
  │  成功：ack；失败：不 ack，留 PEL 等下一轮认领重放
```

### 7.4 关键语义

| 语义 | 实现 | 为什么 |
|---|---|---|
| **at-least-once** | 成功才 `XACK`；失败/崩溃留 PEL | 宁可重复，不可丢 |
| **消费者组** | `consolidators` 组，多个 worker 各持 consumer name | 水平扩展不加代码 |
| **偏移量** | group `last-delivered-id` 在 Redis 侧 | 消费者无状态，随便杀 |
| **孤儿认领** | `XAUTOCLAIM min_idle_time=30s` | 崩溃残留重放，但不抢正在处理的消息 |
| **幂等** | `encode` 用内容哈希；重复 consolidate 被 `MemoryConflictError` 吸收 | at-least-once 的“可重复” |
| **毒丸防护** | 载荷损坏的消息直接 ack | 否则永久重放卡死队列 |

### 7.5 代码落点

- `engram/backend/agents/middlewares/memory_consolidation_middleware.py`
- `engram/backend/agents/memory/worker.py`
- `engram/backend/agents/memory/stream_queue.py`
- `engram/backend/agents/memory/consolidation_worker.py`
- `engram/backend/agents/memory/bootstrap.py`（`_StreamModeWorker` 进程内消费线程）
- `engram/backend/agents/memory/strategies/default/manager.py`（`encode` / `consolidate` 幂等）

### 7.6 关键设计与反方案

**为什么不用 pub/sub？**

- pub/sub 是 fire-and-forget：没有消费者在线时消息直接丢；
- 没有消费位点（offset）、没有 pending、没有 ack；
- 巩固任务需要“重启后还能补”，pub/sub 不满足。

**为什么不用 list？**

- list 没有消费者组语义、没有 pending/ack；
- 多 worker 消费需要自己做锁/偏移量；
- Stream 原生提供 group + PEL + XAUTOCLAIM。

**为什么允许重复？**

- at-least-once 比 exactly-once 简单可靠；
- `encode` 用内容哈希去重，`consolidate` 同 merged_content 同 id 幂等；
- 重复处理最多浪费一次 LLM 调用，不会产生重复记忆。

**为什么要有独立 worker 进程？**

- Web 进程重启不打断巩固；
- 独立进程可水平扩展消费者；
- Web 进程内仍保留轻量消费线程，保证单机部署也能跑。

### 7.7 Trade-off

- **减少**：主对话阻塞、任务丢失、消费者状态管理。
- **换来**：Redis 依赖、PEL 监控、重复处理、毒丸处理。
- **代价**：没有死信队列（DLQ）；LLM 失败只 log 跳过；进程内回退模式是无界队列 + 无重试。

### 7.8 边界

- 无 Redis 时回退进程内 `queue.Queue`：daemon 线程、无界队列、无重试。
- 独立 worker 进程需要 `ENGRAM_REDIS_URL`；没有 Redis 会退出码 1。
- 重复处理是设计允许的，不是 bug；但业务层要保证幂等。
- 毒丸消息会被 ack 掉，不会重放；这是“避免卡死”的取舍，不是“保证处理”。
- `MemoryWorker._maybe_consolidate` 取的是 store 中最旧的 10 条 episodic，不依赖本轮抽取结果。
- `MemoryConsolidationMiddleware` 的 `turn_count` 实现是 `sum(1 for m in messages if isinstance(m, HumanMessage))`。注释声称“只算用户轮次”，但 `memory_recall` / `context_budget_stop` 等内部注入也是 `HumanMessage`，会被计入。这是一个值得留意的实现/注释偏差。

### 7.9 怎么验证

- `engram/backend/tests/v1/unit/memory/test_stream_queue.py`
  - `test_produce_consume_ack_roundtrip`
  - `test_handler_failure_stays_pending`
  - `test_poison_message_acked`
  - `test_killed_consumer_replays_pending`
  - `test_offset_resume_new_messages_only`
  - `test_web_restart_events_not_lost`
  - `test_live_kill_and_replay`（需要 Redis）
- `engram/backend/tests/v1/unit/memory/test_memory_worker.py`
- `engram/backend/tests/v1/unit/memory/test_bootstrap_worker.py`

### 7.10 面试 30 秒

> 巩固任务不是主对话的一部分。中间件每 N 轮把最近消息 XADD 到 Redis Stream，消费者组用 XREADGROUP 消费，成功才 XACK；失败/崩溃留 PEL，下一轮 XAUTOCLAIM 认领重放，所以是 at-least-once。重复处理靠 encode 的内容哈希和 consolidate 的同 id 幂等吸收。选 Stream 而不是 pub/sub/list，是因为它原生有消费者组、偏移量、pending 和 ack。

### 7.11 小结

这一层的核心不是“异步”，而是“异步 + 不丢 + 可重放 + 可水平扩展”。

---

## 8. 模块 05 — 会话状态、Checkpoint 与运行工件

### 8.1 一句话问题

> 服务重启后，怎么让同一个会话接着跑？跑完以后，怎么知道这次到底发生了什么？

### 8.2 背景

这里有三类“状态”，初学者最容易混：

| 状态 | 存在哪 | 回答什么问题 | 生命周期 |
|---|---|---|---|
| **LangGraph checkpoint** | PG / InMemorySaver | 同一个 `thread_id` 的图状态还能不能继续 | 跨 run、跨重启（PG） |
| **session** | `SessionRegistry`（内存） | `session_id → thread_id` 的网关映射 | 进程内 |
| **run artifacts** | 磁盘 / PG `runs` 表 | 这次 run 停在哪、过程发生了什么、报告在哪 | 单次 run，可回看 |

Engram 把“继续工作”和“回看证据”分开，这是 05 章的核心。

### 8.3 Checkpointer

`get_checkpointer()` 默认返回 `InMemorySaver`；网关 lifespan 里如果配了 `ENGRAM_CHECKPOINT_DSN`（或 `ENGRAM_PG_DSN`）：

1. `create_pg_checkpointer(dsn)` 创建 `AsyncConnectionPool(min_size=1, max_size=5)`；
2. `AsyncPostgresSaver(pool)`；
3. `await saver.setup()` 幂等建表；
4. `set_checkpointer(saver)` 预装单例；
5. 之后 `make_lead_agent()` 编译 graph 时拿到的就是它。

**为什么先建 saver 再 bootstrap？**

- graph 是 `create_agent(checkpointer=...)` 编译时绑定 checkpointer；
- 如果先编译 graph 再换 saver，graph 仍拿旧 saver；
- 所以 lifespan 顺序必须是：先 `set_checkpointer`，再 `factory()`。

**多 worker**

- 每个 uvicorn worker 各持独立连接池；
- 共享同一张 PG 会话表；
- 水平扩展不是“配置出来的”，是存储模型决定的。

**Windows 注意**

- psycopg async 不接受 ProactorEventLoop；
- 网关在 uvicorn 下通常使用 SelectorEventLoop；
- 自己写脚本入口时需要 `loop_factory=asyncio.SelectorEventLoop`。

### 8.4 Run 生命周期

`RunManager.create_run()`：

- 生成 `run_id`（`run-<CST timestamp>-<4 random>`）；
- 选择 `output_dir`：
  - 传了 `thread_dir` → `thread_dir/runs/<run_id>`（CLI 路径）；
  - 没传 → `logs_root/<run_id>`（网关当前路径）；
- 创建 `RunJournal(output_dir/events.jsonl)`；
- 创建 `RunContext`；
- 创建 `RunRecord(status=PENDING)`；
- 写 `record.json`。

状态转移：

```text
PENDING → RUNNING → SUCCESS
                  ↘ ERROR
```

`mark_running` / `mark_success` / `mark_failed` 都会重写 `record.json` 并追加 journal 事件。

`RunContext` 提供：

- `record_path` → `output_dir/record.json`
- `events_path` → `output_dir/events.jsonl`
- `artifacts_dir` → `output_dir/artifacts`

### 8.5 运行工件

| 工件 | 作用 |
|---|---|
| `record.json` | 当前 run 的状态快照（status / timestamps / model / error / tokens） |
| `events.jsonl` | 逐事件 JSONL（agent/model/tool/run 生命周期） |
| `artifacts/` | 报告等产物（`final_report.md` / `report.md`） |

`RunJournal.append()` 每次写一条 JSON + 空行，父目录自动创建。`RunJournalMiddleware` 负责把 hook 事件写进去：

- `agent.started` / `agent.finished`
- `llm.request` / `llm.response`
- `tool.called` / `tool.finished`
- `run.started` / `run.finished` / `run.failed`
- `memory.encode` / `memory.consolidate` / `memory.reconsolidate`
- `compaction.*` / `help.requested` / `tool.failure_streak` 等

### 8.6 PGRunStore：运行历史的持久投影

`PGRunStore` 把 `RunRecord` upsert 到 `runs` 表。**当前只有 `app/gateway/research.py` 的 `/research` 路径调用 `_track()` 做投影**；`/chat` 路径会建 run、写 journal，但不会 upsert 到 `runs` 表（代码现状，见边界）。

- `run_id PK`
- `thread_id` / `user_id`
- `status` / `created_at` / `updated_at` / `started_at` / `finished_at`
- `model_name` / `error` / `total_tokens`
- `metadata JSONB`
- `report_path TEXT`

网关的 `research.py` 在 run 状态转移点调用 `_track()` → `store.upsert()`；成功后再写 `report_path`。即使报告写失败，也不会把已成功的 run 翻成 ERROR（post-success bookkeeping 独立 try）。

### 8.7 代码落点

- `engram/backend/agents/runtime/checkpointer.py`
- `engram/backend/agents/runtime/pg_checkpointer.py`
- `engram/backend/agents/runtime/run_manager.py`
- `engram/backend/agents/runtime/run_context.py`
- `engram/backend/agents/runtime/run_record.py`
- `engram/backend/agents/runtime/pg_run_store.py`
- `engram/backend/agents/journal/run_journal.py`
- `engram/backend/agents/middlewares/run_journal_middleware.py`
- `engram/backend/app/gateway/main.py`（lifespan 顺序）

### 8.8 关键设计与反方案

**为什么不用内存 saver 就够？**

- 单机 CLI 够用；
- 网关重启/多 worker 就不够：内存 saver 只在一个进程里；
- PG saver 让同一 `thread_id` 的状态跨进程可见。

**为什么 session 和 run artifact 要分开？**

- session 服务“继续工作”：history、memory、checkpoint；
- run artifact 服务“回看证据”：状态、事件、报告；
- 混在一起会导致“恢复时不知道信哪份状态，复盘时不知道哪些是主状态”。

**为什么还要 PGRunStore，而不是只读 JSON？**

- 进程重启后，内存 `RunManager._records` 没了；
- 散落 JSON 无法按 thread 查询；
- PG `runs` 表提供跨重启、跨 worker 的 query API。

**为什么 `record.json` 和 `events.jsonl` 分开？**

- `record.json` 是快照，适合“现在停在哪”；
- `events.jsonl` 是事件流，适合“过程发生了什么”；
- 快照覆盖写，事件追加写；两者语义不同。

### 8.9 Trade-off

- **减少**：重启丢状态、多 worker 不可用、复盘靠整段聊天记录。
- **换来**：PG 依赖、连接池管理、lifespan 顺序约束、Windows loop 兼容问题。
- **代价**：`SessionRegistry` 仍是内存；网关重启后 `session_id → thread_id` 映射会丢（见边界）。

### 8.10 边界（重要）

- **`SessionRegistry` 是进程内内存**：`session_id → thread_id` 不持久化。PG checkpointer 保存的是 `thread_id` 下的图状态；如果网关重启，旧的 `session_id` 找不到对应 `thread_id`，客户端需要重新建会话。README 的“重启不失忆”要区分“agent 进程重启”与“网关进程重启”。
- **网关 run 目录形状**：`RunManager.create_run()` 在网关调用时没传 `thread_dir`，所以 `output_dir = logs_root/<run_id>`；CLI 路径是 `logs_root/threads/<thread_id>/runs/<run_id>`。读代码时不要假设两者一致。
- **运行历史端点依赖 PG**：没有 `ENGRAM_RUNS_PG_DSN` 或 checkpointer DSN 时，`/sessions/{id}/runs` 和 `/runs/{id}/report` 返回 503。
- **`/chat` 的 run 不投影到 PGRunStore**：`research.py` 有 `_track()`，`chat.py` 没有；因此 `GET /sessions/{id}/runs` 当前主要反映 research 运行，不是所有 chat 运行。读接口时不要假设“所有 run 都在 PG”。
- **PGRunStore 是投影，不是真相**：真相是 `RunManager` + `record.json` + artifacts；PG 表是 query 层。
- **报告产物路径**：`_write_report_fallback()` 优先找 `final_report.md` / `report.md`，都没有才写聚合 fallback；`report_path` 始终可解析。

### 8.11 怎么验证

- `engram/backend/tests/v1/unit/gateway/test_pg_checkpointer.py`
  - `test_fallback_inmemory_without_dsn`
  - `test_set_checkpointer_preloads_singleton`
  - `test_lifespan_preloads_pg_saver_before_bootstrap`
  - `test_state_recovers_across_saver_instances`（live，需 PG）
- `engram/backend/tests/v1/unit/runtime/test_run_manager.py`
- `engram/backend/tests/v1/unit/journal/test_run_journal.py`
- `engram/backend/tests/v1/unit/gateway/test_sessions_api.py`
- `engram/backend/tests/v1/unit/gateway/test_research_api.py`

### 8.12 面试 30 秒

> Engram 把状态分成两层：LangGraph checkpointer 负责“同一个 thread 还能不能继续”，run artifact 负责“这次到底发生了什么”。配了 PG DSN 时，lifespan 会先建 AsyncPostgresSaver 并预装单例，再编译 graph，所以重启后同一 thread 能读回状态；run 这边用 record.json + events.jsonl + artifacts 记录状态、过程、报告，并用 PGRunStore 投影到 runs 表供跨重启查询。

### 8.13 小结

恢复和复盘不是同一件事。checkpoint 让你接着跑，run artifact 让你解释为什么这么跑。

---

## 9. 模块 06 — SSE 流式与断线续传

### 9.1 一句话问题

> 怎么把模型的思考、工具调用、答案实时吐给客户端；连接断了，又怎么只补缺口而不是从头再来？

### 9.2 背景

研究任务可能跑几十秒甚至更久。用户需要看到：

- `thinking`：推理 token；
- `answer`：答案文本增量；
- `tool_start` / `tool_end`：工具调用；
- `budget_update` / `sandbox_update`：运行状态；
- `done` / `error`：终止。

如果只返回一个最终字符串，用户只能看转圈。SSE 是 HTTP 上的单向事件流，天然适合“服务端持续推”；每帧可以带 `id:`，客户端重连时用 `Last-Event-ID` 告诉服务端“我收到哪了”。

### 9.3 流式服务

`EngramStreamClient.stream()` 消费：

```python
graph.astream(
    state,
    config=config,
    stream_mode=["values", "messages", "custom"],
)
```

三种 mode：

| mode | 内容 | 用途 |
|---|---|---|
| `messages` | token 级 `AIMessageChunk` / `ToolMessage` | thinking / answer / tool_start / tool_end |
| `values` | 完整状态快照 | 去重、done 检测、budget/sandbox 状态 |
| `custom` | middleware/strategy 用 `get_stream_writer()` 发的事件 | compaction_start/end 等 |

**去重与过滤**

- `seen_ids` / `streamed_ids`：按 `msg_id` 去重，避免 values 帧重复输出；
- 第一帧 values 先预填旧 messages，防止 checkpoint 恢复后重放历史；
- `internal_llm` tag：过滤 summarizer / reporter / reflection / skill-selector 等内部调用，防止泄漏成 answer；
- SkillSelector 的 JSON 输出可能跨多个 delta，无法逐 delta 判断，所以按 `msg_id` 累积缓冲，检测 `{"skills": [...]}` 后丢弃；
- 渲染层再用 `_strip_skills_leak()` 兜底清洗残留 JSON。

### 9.4 SSE 帧与缓冲

`chat.py` 把 `StreamEvent` 变成：

```text
id: 42
event: answer
data: {"type": "answer", "content": "..."}

```

每帧带递增 id。`SSEEventBuffer`：

- per-session 环形缓冲，默认容量 `500`；
- `append(frame)` 分配 id；
- `replay_after(last_id)` 返回缺口事件；
- 如果 `last_id < first_id - 1`，说明缺口已超出缓冲，返回空，并让 `chat.py` 发一条 `error: resume gap exceeded buffer capacity`；
- 响应头 `X-Engram-Events-Dropped: true` 明示有事件被容量淘汰。

**重连流程**

```text
Client 在第 5 帧断线
  → 重连带 Last-Event-ID: 5
  → 服务端先 replay_after(5) 补发 6,7...
  → 再继续实时流
```

**与 Redis Stream 的同构**

| | Redis Stream 巩固队列 | SSE 网关 |
|---|---|---|
| 偏移量 | group last-delivered-id | Last-Event-ID（客户端持有） |
| 断点重放 | PEL + XAUTOCLAIM | per-session 环形缓冲 |
| 语义 | at-least-once | at-least-once（客户端按 id 幂等） |
| 超界 | 无 DLQ（当前） | `X-Engram-Events-Dropped` 明示 |

### 9.5 代码落点

- `engram/backend/app/services/stream_service.py`
- `engram/backend/app/gateway/chat.py`
- `engram/backend/app/gateway/research.py`
- `engram/backend/app/gateway/sse_buffer.py`
- `engram/backend/app/schemas/chat.py`

### 9.6 关键设计与反方案

**为什么用 SSE，不用 WebSocket？**

- 服务端 → 客户端单向流，SSE 足够；
- SSE 是普通 HTTP，网关/代理兼容性好；
- `id:` + `Last-Event-ID` 是规范原生续传机制，不需要自己设计协议；
- 代价：只能服务端推，客户端不能在同一条连接上发消息（Engram 用新 POST 重连）。

**为什么缓冲放内存，不放 Redis？**

- 会话级生命周期短；
- 重启即新会话，旧连接本来也断了；
- 内存实现简单、无额外依赖；
- 代价：网关重启后缓冲丢失，超出容量的缺口无法补。

**为什么错误只回异常类型？**

- 防止 DSN、路径、凭据等细节泄漏给客户端；
- 详情留服务端日志；
- 错误后仍发 `done`，客户端统一等 done 判终止。

### 9.7 Trade-off

- **减少**：轮询、长连接协议复杂度、断线重放开销。
- **换来**：事件去重、selector 泄漏处理、缓冲容量限制、SSE 代理配置。
- **代价**：缓冲 500 帧是固定值；超出后只能明示丢事件，不能补齐。

### 9.8 边界

- 缓冲默认 500 帧；超出容量的缺口无法补，只能报错。
- 缓冲在内存；网关重启后丢失。
- SSE 是 at-least-once：补发可能重复，客户端应按 event id 幂等。
- `chat` 端点用同步 `def` 返回 `StreamingResponse`；真正的流在 async generator 里。阻塞 IO 用 `asyncio.to_thread` 挪线程池。
- `research` 端点成功后的报告写入是独立 try：失败只 log，不把成功 run 翻成 ERROR。
- 事件类型以 `stream_service.py` 的 `StreamEvent.type` 为准；新增事件要同时考虑 CLI/TUI 渲染。

### 9.9 怎么验证

- `engram/backend/tests/v1/unit/gateway/test_sse_resume.py`
  - `test_resume_fills_gap_after_disconnect`
  - `test_resume_without_header_is_fresh_stream`
  - `test_buffer_semantics_gap_beyond_capacity`
  - `test_frames_carry_id_header`
- `engram/backend/tests/v1/unit/gateway/test_chat_api.py`
- `engram/backend/tests/v1/unit/gateway/test_research_api.py`
- `engram/backend/tests/v1/unit/services/test_stream_service.py`

### 9.10 面试 30 秒

> 网关不走 `LeaderAgent.run`，而是直接用 `graph.astream` 消费 `messages/values/custom` 三种流，把 token delta、工具事件、预算状态标准化成 StreamEvent，再包成带 `id:` 的 SSE 帧。每个 session 有一个 500 帧的环形缓冲；客户端断线重连带 `Last-Event-ID`，服务端先补缺口再接实时流。缺口超出容量时用 `X-Engram-Events-Dropped` 明示，不装作没丢。这个语义和 Redis Stream 的 PEL 重放是同一套心智模型。

### 9.11 小结

流式不是“把结果分块发”，而是“事件标准化 + 去重 + 断点续传 + 诚实降级”。

---

## 10. 模块 07 — 工具、沙箱与 MCP 安全边界

### 10.1 一句话问题

> 模型拿到文件读写和 shell 执行能力以后，怎么保证它不会越界、不会误用、不会被外部工具描述注入？

### 10.2 背景

工具层最容易被误解成“能力清单”：能读文件、能搜、能跑 shell，听起来越多越好。真正难的是：

- 模型可能发明不存在的工具；
- 参数可能非法；
- 路径可能逃出工作区；
- shell 可能执行破坏性命令；
- MCP server 的工具描述可能包含 prompt injection；
- 错误信息可能泄漏凭证。

Engram 的工具层不是“多接几个工具”，而是“把动作收进一条受控执行链”。

### 10.3 工具来源

| 来源 | 例子 | 加载方式 |
|---|---|---|
| builtin | `web_search` / `browse_page` / `read_snapshot` / `skill_search` | `get_available_tools(groups=["core"])` |
| sandbox | `bash` / `read_file` / `write_file` / `list_dir` / `str_replace` / `present_files` | `make_sandbox_tools(provider)` |
| MCP | 外部 server 暴露的 tools | `McpLoader` + `ToolRegistry` |

分组：

- `core`：default + expert 都加载；
- `deferred`：仅 expert 加载；
- `sandbox`：sandbox provider 启用时加载。

### 10.4 沙箱组合模型

`Sandbox` 不是 ABC，而是组合 `Runtime + Translator + Guard`：

```text
validate → translate → execute → mask
```

| 组件 | 职责 |
|---|---|
| `SecurityGuard` | 路径/命令校验 |
| `PathTranslator` | 虚拟路径 ↔ 宿主/容器路径 |
| `SandboxRuntime` | 真正执行（LocalRuntime / DockerRuntime） |

切换沙箱（Local / Docker / E2B）只换组件，编排逻辑复用。

**LocalSandboxProvider**

- 确定性 `sandbox_id = sha256(user:thread)[:8]`；
- 按 thread 复用 sandbox；
- LRU 缓存默认 256；
- 驱逐时锁外 `close()`，避免持锁阻塞 IO；
- 但本质是宿主进程执行，不是隔离。

**LocalSecurityGuard**

- 拒绝 `..` 路径穿越；
- 路径必须在白名单映射内（`/mnt/engram/user-data/...`）；
- 写只读路径拒绝；
- bash 命令先做危险模式黑名单（`rm -rf /`、`mkfs`、fork bomb、`curl | bash`、`eval`、`exec`、`source`）；
- `shlex.split()` 失败 → fail-closed（畸形引号也拒绝）；
- 命令中的绝对路径必须在白名单或系统路径 `/bin/` `/usr/` `/lib/` 内。

**DockerPathGuard**

- 写路径必须在 `/mnt/engram/user-data/`；
- bash 重定向目标（绝对路径）必须在挂载区；
- 读不限制，靠容器隔离兜底。

**工具细节**

- `write_file` 非 append 模式上限 5MB；
- `bash` 输出截断 10,000 字符；
- `str_replace` 按 `(sandbox, path)` 加文件锁，防并发写冲突；
- `present_files` 要求路径在 `/mnt/engram/user-data/`，否则抛错。

### 10.5 MCP 安全层

`McpLoader` 的启动流程：

1. `EnvFilter.check_env(server.env)`：只把安全环境变量 + config 显式声明传给 stdio 子进程；宿主 `AWS_KEY` / `GITHUB_TOKEN` 不会整包继承；
2. `MultiServerMCPClient` 连接；
3. `asyncio.wait_for(client.get_tools(), timeout=connect_timeout)`；
4. `include_tools` / `exclude_tools` 过滤；
5. `DescriptionScanner.scan_description()`：检测 `ignore previous instructions` / `system prompt` / `you are now` / `forget everything` / `reveal your instructions`；
6. 注册到 `ToolRegistry`，每个工具带 `CircuitBreaker`；
7. `CredentialSanitizer` 在错误信息回 LLM 前清洗 `ghp_*` / `sk-*` / `Bearer *` / `token=*`。

**失败隔离**

- `load_startup()` 用 `asyncio.gather(..., return_exceptions=True)`；
- 单个 server 失败不阻塞其他 server；
- `McpManager` 提供 fallback chain：`server:tool` / `builtin:tool` / `sandbox:tool`，按链查首个 healthy；
- `CircuitBreaker` 状态机：closed → open → half-open。

### 10.6 代码落点

- `engram/backend/agents/sandbox/sandbox.py`
- `engram/backend/agents/sandbox/local/local_sandbox_provider.py`
- `engram/backend/agents/sandbox/guards/local_security_guard.py`
- `engram/backend/agents/sandbox/guards/audit_guard.py`
- `engram/backend/agents/sandbox/guards/docker_path_guard.py`
- `engram/backend/agents/sandbox/integration/tools.py`
- `engram/backend/agents/mcp/loader.py`
- `engram/backend/agents/mcp/registry.py`
- `engram/backend/agents/mcp/guards/env_filter.py`
- `engram/backend/agents/mcp/guards/description_scanner.py`
- `engram/backend/agents/mcp/guards/credential_sanitizer.py`
- `engram/backend/agents/middlewares/sandbox_middleware.py`
- `engram/backend/agents/middlewares/tool_call_middleware.py`

### 10.7 关键设计与反方案

**为什么沙箱用组合，不用继承？**

- Local / Docker / E2B 的差异在 runtime、translator、guard；
- 编排顺序（validate → translate → execute → mask）是共同的；
- 组合让“换后端只换组件”，编排逻辑复用，测试可以 mock 单个组件。

**为什么本地沙箱还要做命令扫描？**

- Local sandbox 是宿主进程执行，没有容器隔离；
- 黑名单 + 白名单 + shlex fail-closed 是 defense-in-depth；
- 但它不是完整隔离，不能替代 Docker。

**为什么 MCP 要扫描工具描述？**

- 工具描述会进入模型上下文；
- 恶意 server 可以在描述里写 “ignore previous instructions”；
- 扫描是注册前的第一道门，拒绝可疑工具。

**为什么环境变量要白名单？**

- stdio MCP 子进程如果继承宿主环境，会把 API key / token 带进第三方进程；
- 白名单只传 PATH/HOME/LANG 等定位变量 + config 显式声明的变量。

**为什么工具结果要脱敏？**

- 错误信息可能包含 DSN、token、路径；
- 回给模型前清洗，避免二次泄漏到 prompt / trace。

### 10.8 Trade-off

- **减少**：越界写、破坏性命令、凭证泄漏、恶意工具描述。
- **换来**：白名单维护、误拒（LLM 需重试）、MCP 连接复杂度、容器依赖。
- **代价**：Local 模式的规则不是完整隔离；Docker 模式需要镜像、端口、WSL 配置。

### 10.9 边界

- **Local sandbox 不是隔离**：它是宿主进程 + 规则校验；真正隔离要用 Docker sandbox。
- DockerPathGuard 只检查绝对路径重定向；不解析 `cd` 后的相对路径，不检查 `tee`，靠容器隔离兜底。
- MCP 描述扫描是正则黑名单，不是完整 injection 防御；不能保证零误判/零漏判。
- 工具结果脱敏只作用于错误信息；正常 tool result 不清洗。
- `ToolCallMiddleware` 的重试/硬预算当前放宽到 999（用户要求取消限制）；不要把它当成强约束。
- `LoopDetectionMiddleware` 未挂载。

### 10.10 怎么验证

- `engram/backend/tests/v1/unit/sandbox/`（39 个测试文件）
- `engram/backend/tests/v1/unit/mcp/test_guards_selfcheck.py`
- `engram/backend/tests/v1/unit/mcp/test_loader_selfcheck.py`
- `engram/backend/tests/v1/unit/mcp/test_registry_selfcheck.py`
- `engram/backend/tests/v1/unit/middlewares/test_tool_call_failure_summary.py`

### 10.11 面试 30 秒

> Engram 的工具层不是“给模型一堆函数”，而是把动作收进一条受控链：工具先按来源注册，sandbox 用 `validate → translate → execute → mask` 组合 runtime/translator/guard，Local 模式有路径穿越拒绝、白名单、危险命令黑名单和 shlex fail-closed，Docker 模式有挂载区写限制。MCP 侧在注册前做 env 白名单、工具描述注入扫描、错误凭证脱敏，并用熔断和 fallback 隔离坏 server。

### 10.12 小结

工具治理的重点不是“能力多”，而是“动作有边界、失败可解释、越界可拦截、凭证不泄漏”。

---

## 11. 模块 08 — 多 Agent、Skill 与自进化

### 11.1 一句话问题

> 当单个 Agent 的能力不够时，怎么把子任务委派出去？当一类任务反复出现时，怎么把过程知识沉淀成可复用的 Skill？

### 11.2 背景

Engram 的主 Agent 是研究助手，不是万能 coding CLI。它需要：

- **Specialist**：把 coding 子任务交给外部 CLI（pi / codex / claude）；
- **Subagent**：把子任务交给自己的一个 leaf 副本（同模型、隔离上下文、共享 sandbox）；
- **Skill**：把“怎么验证来源 / 怎么做文献综述 / 怎么调试”这类过程知识，以提示词形式注入；
- **Evolution / Eval**：根据指标自动改写 Skill 或 Specialist 的模板，并用 gate 控制回滚。

这些能力**默认多数关闭**，是可选层，不是主链路。

### 11.3 Specialist

`SpecialistAgent` 是 Protocol，黑盒：

- 自带 model；
- 自管 ReAct loop；
- 自管 context；
- Engram 只传 `goal + context_summary + sandbox_id`；
- 返回 `SpecialistRawResult`（raw output + artifacts + usage + duration + exit_code）。

`setup_multiagent()`：

1. 读 `MultiAgentConfig`；
2. `enabled=false` → 返回空 setup，lead agent 行为不变；
3. 按 `specialists_use` 反射加载；
4. 凭证缺失 → specialist disabled，工具不注册；
5. `SpecialistRegistry` 注册；
6. 生成 `delegate_to_<name>` 工具；
7. `SubagentRuntime` + `delegate_to_subagent`（如果未把 subagent 作为 specialist）；
8. `OrchestrationMiddleware` + metrics；
9. L2/L3 层按配置装配。

**Subagent 的 leaf 约束**

`_subagent_factory()` 构造的 leaf lead agent：

- `specialist_tools=None`：看不到 `delegate_to_*`，不能再 spawn；
- `orchestration_middleware=None`：不挂编排；
- 目的：`max_spawn_depth=1`，防止递归 spawn。

### 11.4 Skill

Skill 是**研究过程知识包**，不是可执行函数：

> “怎么验证一个来源”是 Skill；“执行一次 web 搜索”是 Tool。

`SkillRecord`：

- `skill_id` / `name` / `path` / `content_hash`
- `is_active` 单指针
- `lineage`（版本血缘）
- `allowed_tools`
- 4 计数器：`selections` / `applied` / `completions` / `fallbacks`
- 4 rate：`applied_rate` / `completion_rate` / `effective_rate` / `fallback_rate`

`SkillSelector.select_for_task()`：

1. override 强制包含（`/skill <name>`）；
2. quality filter：`effective_rate < threshold AND total_selections >= min` 淘汰；
3. 候选 ≤ `max_skills` → 全返，跳过 LLM；
4. 候选 > max 且有 LLM → LLM 选 ≤ max；
5. LLM 失败/无 LLM → 按 `effective_rate` 降序 fallback。

`SkillInjectionMiddleware`：

- `before_model` 注入 active skills；
- 注入是 `SystemMessage`，会增加 prompt 前缀；
- `SkillMetricsMiddleware` 在 `wrap_tool_call` 标记 applied，`after_agent` 归因 completions/fallbacks。

**Skill 文件格式**：每个 skill 一个目录，含 `SKILL.md`，frontmatter + body。当前 `engram/backend/agents/skill/builtin_skills/` 下有 37 个 `SKILL.md`，其中 core 12 个启动时自动加载；`USAGE.md` 文字写的是 36 个，可能是旧数字，以代码为准。

### 11.5 Evolution / Eval

- **Layer 2 Evolution**：`MetricMonitor` 触发 → `IVEFocuser` 诊断 → `LLMMutator` 改写 → `ScoreDeltaGate` 比分数 → `GitRatchet` 退化回滚；
- **VersionDAG**：`evolution_artifacts` + `evolution_experiments` 表，`is_active` 单指针，支持 rollback；
- **Layer 3 Eval**：`SkillJudgmentAnalyzer` / `TaskQualityJudge` / `ResponseContractChecker` / `RuntimeTracker`；
- 默认 `ENGRAM_SKILL_EVOLVE_ENABLED=false`、`ENGRAM_SKILL_EVAL_ENABLED=false`。

### 11.6 代码落点

- `engram/backend/agents/multiagent/bootstrap.py`
- `engram/backend/agents/multiagent/registry.py`
- `engram/backend/agents/multiagent/specialist.py`
- `engram/backend/agents/multiagent/runtimes/subagent_runtime.py`
- `engram/backend/agents/multiagent/tools.py`
- `engram/backend/agents/multiagent/metrics.py`
- `engram/backend/agents/skill/selector.py`
- `engram/backend/agents/skill/injector.py`
- `engram/backend/agents/skill/types.py`
- `engram/backend/agents/skill/store.py`
- `engram/backend/agents/skill/evolution/`
- `engram/backend/agents/skill/eval/`
- `engram/backend/agents/multiagent/evolution/version_dag.py`

### 11.7 关键设计与反方案

**为什么 Specialist 是黑盒？**

- 外部 CLI 有自己的模型、工具、上下文；
- Engram 不需要理解它的内部循环；
- 只传 goal + context summary + sandbox，拿回 raw result；
- 这样新增 specialist 不需要改主 Agent。

**为什么 Subagent 要 leaf-only？**

- 防止递归 spawn 导致任务爆炸；
- leaf 不挂 orchestration，不能再 delegate；
- 共享父 sandbox，避免环境分裂。

**为什么 Skill 不直接做成 Tool？**

- Skill 是“怎么做”的知识，影响模型决策；
- Tool 是“能做什么”的能力，执行动作；
- Skill 注入 prompt，Tool 进入工具表；
- 两者混在一起会让工具表膨胀、权限边界模糊。

**为什么 Evolution 要有 VersionDAG / rollback？**

- LLM 改写可能退化；
- 需要保留历史版本、比较分数、失败回滚；
- `is_active` 单指针让 hot swap 简单；
- `hash_exists_in_recent` 防止近 5 版循环。

### 11.8 Trade-off

- **减少**：主 Agent 能力面、重复造工具、手工维护 skill。
- **换来**：外部 CLI 依赖、凭证管理、版本/评测复杂度。
- **代价**：specialist 可能不可用；skill 质量依赖指标与 LLM judge；evolution 可能改坏，需要 gate 兜底。

### 11.9 边界

- 默认 `ENGRAM_MULTIAGENT_ENABLED=true`，但 specialist 需要外部 CLI + 凭证；缺失时 disabled。
- `ENGRAM_SKILL_ENABLED=false` 默认关闭；当前代码内置 37 个 `SKILL.md`，core 12 个自动加载（`USAGE.md` 写 36，可能是旧数字）。
- Skill 搜索按英文子串匹配；中文查询可能找不到。
- L2/L3 默认关闭；开启后依赖指标积累，冷启动数据不足。
- Specialist 是外部进程，行为不受 Engram 完全控制；sandbox 共享不等于安全隔离。
- `Subagent` 是同一模型副本，不是独立能力增强；它解决上下文隔离，不解决模型能力。

### 11.10 怎么验证

- `engram/backend/tests/v1/unit/multiagent/`（60 个测试文件）
- `engram/backend/tests/v1/unit/skill/`（40 个测试文件）
- `engram/backend/tests/v1/unit/multiagent/eval/`
- `engram/backend/tests/v1/unit/multiagent/evolution/`
- `engram/backend/tests/v1/unit/skill/evolution/`

### 11.11 面试 30 秒

> Engram 的可扩展层分三块：Specialist 把 coding 子任务委派给外部 CLI，Engram 只传 goal、上下文摘要和 sandbox，不关心它内部怎么跑；Subagent 是自己的 leaf 副本，不能继续 spawn，用来隔离上下文；Skill 是提示词层面的过程知识，不是工具，按质量指标选择注入。Evolution 和 Eval 是可选层，用 VersionDAG 和回滚 gate 控制改写风险，默认关闭。

### 11.12 小结

多 Agent 和 Skill 不是“越多越强”，而是“把不擅长的事委派出去，把反复出现的知识沉淀下来”。

---

## 12. 模块 09 — 测试与评测体系

### 12.1 一句话问题

> 怎么证明这套系统不是“跑通一次”，而是“在固定条件下稳定可复现”？

### 12.2 测试规模

本次在本地实测：

```text
2764 passed, 12 skipped in 90.20s
```

- 253 个测试文件；
- 测试目录：`engram/backend/tests/v1/unit/` + `v1/integration/`；
- 覆盖：memory 28 文件、sandbox 39、skill 40、multiagent 60、middleware 9、gateway 5、context 4、runtime 5、MCP 8。

> README 写的是 2,764 个测试，与本次实测一致。`pytest --collect-only` 的数字可能因环境/插件略有差异，以实际运行为准。

### 12.3 测试分层

| 层 | 例子 | 证明什么 |
|---|---|---|
| **单元** | `test_tiered_store.py` / `test_stream_queue.py` / `test_default_strategy.py` | 机制按设计工作 |
| **集成** | `test_minimum_agent_loop.py` / `test_default_strategy_e2e.py` / `test_cli_chat.py` | 多层拼起来能跑 |
| **live** | `test_live_flush_hot_recall_from_cold` / `test_live_kill_and_replay` / `test_state_recovers_across_saver_instances` | 真实 Redis/PG 语义 |
| **协议/自检** | `test_guards_selfcheck.py` / `test_loader_selfcheck.py` | 安全 guard / MCP 加载契约 |

**CI**

`.github/workflows/ci.yml`：

- Postgres 16 service container；
- `ENGRAM_TEST_PG_DSN` 指向它；
- 跑全量测试，忽略 `test_stage5_integration.py` / `test_stage6_integration.py`（需要 live sandbox 镜像 + agent-sandbox SDK）；
- 真实 LLM 测试在没有 `DEEPSEEK_API_KEY` 时 self-skip。

**本地跳过**

没有 Redis/PG/真实 LLM 时，live 测试会 skip；这不是“测试没跑”，而是“诚实的测试边界”。

### 12.4 测试哲学

从 `docs/interview-notes.md` 和测试代码可以总结出三条：

1. **外部行为测试**：HTTP 语义、SSE 帧序列、Stream 组语义；
2. **内部靠注入缝**：`runtime_factory` / `store` / `graph fake`，测试不碰真实 provider/网络；
3. **live 测试真跑**：CI 挂 Postgres/Redis service，恢复/重放/兜底语义实测；本地无依赖显式 skip，不靠 mock 骗绿。

### 12.5 这些测试不证明什么

- 不证明模型回答质量；
- 不证明所有真实仓库任务都能跑；
- 不证明 Local sandbox 是安全的；
- 不证明 Skill/Evolution 在你开启后一定有效；
- 不证明网关重启后 session 映射还在（见 05 边界）。

### 12.6 怎么加测试

- 新机制：先在对应 `unit/<area>/` 写行为测试；
- 跨层：写 `integration/`；
- 需要真实依赖：标 `live`，无 DSN 时 skip；
- 安全边界：在 `test_guards_selfcheck.py` 补用例；
- 新增 SSE 事件：同时测帧序列与 `Last-Event-ID` 行为。

### 12.7 面试 30 秒

> 这个项目有 2,764 个通过测试、12 个 skip，覆盖单元、集成和 live 三层。单元测试验证机制，集成测试验证多层拼起来能跑，live 测试在 CI 的 Postgres/Redis service 上真跑恢复/重放/兜底语义；本地没有依赖时显式 skip，不靠 mock 骗绿。测试主要证明 harness 契约稳定，不证明模型能力上限。

### 12.8 小结

测试数量不是目的。真正有价值的是：每个核心设计都有对应的行为测试，且测试边界诚实。

---

## 13. 当前边界与演进方向

这一节是写给自己和面试官看的：**哪些是当前真实边界，哪些是下一步**。

### 13.1 当前边界

| 边界 | 现状 | 影响 |
|---|---|---|
| Session 映射不持久 | `SessionRegistry` 进程内内存 | 网关重启后 `session_id → thread_id` 丢失；PG checkpointer 仍保留 thread 状态 |
| 默认记忆关闭 | `.env.example` `ENGRAM_MEMORY_USE=` 为空 | 裸 pip 启动不启用记忆；Docker Compose 才打开 |
| 热层 TTL 默认未启用 | 不设 `ENGRAM_MEMORY_TTL_SECONDS` 时 `_ttl=None` | 热层不会自然过期；README 的“自然过期”需显式配置 |
| 遗忘策略未接线 | `should_forget()` 无调用点 | `forget.ttl_hours` 不会自动淘汰记忆 |
| 中文分词弱 | BM25 默认 `lower().split()` | 中文记忆召回效果有限 |
| 无默认向量检索 | `vector_store` / `graph_store` 可选叠加 | 语义召回不如向量库 |
| P2/P3 未完成 | P2 无动作；P3 只设 flag | 不要把 pending 当成已实现 |
| Local sandbox 非隔离 | 宿主进程 + 规则 | 不能替代 Docker |
| MCP 描述扫描是黑名单 | 正则模式 | 不是完整 injection 防御 |
| 工具预算放宽 | `_RETRY_BUDGET=999` / `_HARD_BUDGET=999` | 当前没有强循环上限 |
| L2/L3 默认关闭 | 环境变量 false | 自进化/评测不是开箱即用 |
| 网关 run 目录与 CLI 不同 | 网关 `logs_root/<run_id>`；CLI `threads/<thread_id>/runs/<run_id>` | 读日志时注意路径 |
| `/chat` 不投影 PGRunStore | 只有 `/research` 调 `_track()` | `/sessions/{id}/runs` 不等于全部 chat 运行 |
| 巩固 turn_count 含内部消息 | 只按 `isinstance(HumanMessage)` 计数 | `memory_recall` 等注入会推高触发频率 |
| 文档数字有漂移 | `USAGE.md` 写 36 个内置 skill，代码有 37 个 `SKILL.md` | 以代码/测试为准，引用前先核对 |

### 13.2 如果继续做，优先补什么

1. **持久化 SessionRegistry**：把 `session_id → thread_id` 落 PG/Redis，网关重启也能恢复会话入口。
2. **补中文 tokenizer**：BM25 加 jieba 或字符 n-gram；否则中文记忆召回是明显短板。
3. **完成 P2/P3**：把 thinking 压缩、observations top-N 真正接进渲染层。
4. **统一 run 目录形状**：网关也传 `thread_dir`，让 CLI 与网关日志路径一致。
5. **增强 consolidation 可观测性**：PEL 深度、重放次数、失败分类、DLQ。
6. **把 Local sandbox 的边界写进启动提示**：避免用户误以为本地模式是隔离。
7. **补 benchmark / 回归任务**：当前测试强在契约，弱在真实任务效果。

---

## 14. 面试表达

### 14.1 30 秒项目介绍

> Engram 是一个本地 AI 研究助手，用 LangGraph 构建 ReAct Agent，外面套 FastAPI 网关。它主要解决三个问题：跨会话记忆用 Redis 热层 + Postgres 冷层，会话状态用 PG checkpointer 持久化，流式输出用 SSE + Last-Event-ID 支持断线续传。Agent 外面有一层中间件治理上下文、记忆召回、工具账本、沙箱/MCP 安全和报告。项目有 2,764 个通过测试。

### 14.2 1 分钟架构

> 一条请求从网关进来，先由 SessionRegistry 把 session_id 映射到 thread_id，RunManager 建 run 和 journal，然后 EngramStreamClient 直接消费 `graph.astream`。Graph 是 `create_agent` 编译的 ReAct 循环，before_model 做上下文治理、记忆召回、skill 注入，after_model 做预算、工具账本、停滞检测，工具调用经过 sandbox/MCP 边界，after_agent 合成报告。旁路有三条：PG checkpointer 保存图状态，RunJournal 写事件，PGRunStore 投影 run 历史。最后 StreamEvent 被包成带 id 的 SSE 帧，per-session 环形缓冲支持 Last-Event-ID 补发。

### 14.3 3 分钟深挖（选一个模块）

以记忆为例：

> 记忆层我把“快”和“全”分开。Redis 热层用 `engram:mem:{user}:{thread}:{trace_id}` 分区，每条带 TTL，读命中续命；Postgres 冷层存全量 JSONB，不淘汰。写路径冷先写，因为冷层是持久性保证；读路径热先读，miss 查冷并回填热。检索默认 BM25，复合分数 0.7 相似度 + 0.3 Ebbinghaus 强度，命中会强化写回。巩固是异步的：中间件每 N 轮把最近消息 XADD 到 Redis Stream，消费者组 XREADGROUP 消费，成功才 XACK，失败留 PEL，重启 XAUTOCLAIM 重放，所以是 at-least-once；重复处理靠内容哈希和 consolidate 幂等吸收。这样热缓存被清空也不会丢记忆，只是首次召回慢一点。

### 14.4 高频追问

| 追问 | 回答要点 |
|---|---|
| 为什么叫 harness，不叫 agent？ | Agent 决定下一步做什么；harness 规定边界、记录、验证、恢复、什么时候算完成 |
| 为什么记忆分两层？ | 热层低延迟 + TTL；冷层全量兜底；冷先写、热先读、冷命中回填 |
| 为什么用 Redis Stream？ | at-least-once、消费者组、PEL、XAUTOCLAIM；pub/sub 会丢，list 没有消费位点 |
| 为什么用 PG checkpointer？ | 重启/多 worker 共享 thread 状态；InMemory 只适合本地 CLI |
| 为什么 SSE 缓冲和 Stream 是同一套语义？ | 偏移量 + 缺口重放；SSE 用 Last-Event-ID，Stream 用 group offset + PEL |
| 为什么 BM25 不用向量？ | 轻、可解释、无 embedding 依赖；代价是中文/语义召回弱；vector 是可选叠加 |
| 为什么中间件顺序不能乱？ | 记忆要在 Sandbox 后、ToolCall 前；pairing 修补要在 before_model；Report 要在 after_agent |
| 为什么 Local sandbox 不是隔离？ | 宿主进程执行 + 规则校验；真正隔离用 Docker |
| 为什么 Skill 不是 Tool？ | Skill 是“怎么做”的知识，注入 prompt；Tool 是“能做什么”的能力，执行动作 |
| 2,764 个测试证明什么？ | 契约稳定、边界行为可复现；不证明模型质量/真实任务上限 |
| 这个项目最大的不足？ | Session 映射不持久、`/chat` 不投影 PGRunStore、中文检索弱、P2/P3 未完成、Local 非隔离、L2/L3 默认关闭 |
| 如果继续做，先做什么？ | 持久化 session 映射 + 中文 tokenizer + 统一 run 目录 + consolidation 可观测性 |

### 14.5 讲数字的纪律

- 本文只引用代码/测试能证实的事实：2,764 passed / 12 skipped / 90.20s；
- 不要编造性能提升、成功率、压缩率；
- 如果引用 README 的“2,764 tests”，说明这是当前仓库的测试规模，不是模型效果；
- 讲测试时，明确“live 测试在无 DSN 时 skip”。

---

## 15. 附录

### 15.1 快速运行

```bash
# 安装
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"
cp .env.example .env              # 填 DEEPSEEK_API_KEY

# 启动网关
uvicorn engram.backend.app.gateway.main:app --port 8000

# 建会话
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

# 流式对话
curl -N -X POST localhost:8000/sessions/$SID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "SSE 断线重连一般怎么做？"}'

# 终端
engram
```

全栈：

```bash
docker compose up -d
```

### 15.2 关键环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 默认 provider key | 空 |
| `ENGRAM_MEMORY_USE` | 记忆 provider；`default` 启用 | 空（禁用） |
| `ENGRAM_REDIS_URL` | 热层 + Stream 队列 | 空 |
| `ENGRAM_MEMORY_PG_DSN` | 冷层 | 空 |
| `ENGRAM_MEMORY_TTL_SECONDS` | 热层 Redis key TTL（秒） | 空（不设置 TTL，热层不过期） |
| `ENGRAM_CHECKPOINT_DSN` | LangGraph PG checkpointer | 空（InMemory） |
| `ENGRAM_RUNS_PG_DSN` | run 历史表 | 空（复用 checkpoint DSN） |
| `ENGRAM_SANDBOX_USE` | sandbox provider 路径 | 空（禁用） |
| `ENGRAM_MCP_ENABLED` | MCP 总开关 | false |
| `ENGRAM_SKILL_ENABLED` | Skill 总开关 | false |
| `ENGRAM_MULTIAGENT_ENABLED` | 多 Agent 总开关 | true |
| `ENGRAM_MULTIAGENT_L2_ENABLED` | 多 Agent 演化 | false |
| `ENGRAM_MULTIAGENT_L3_ENABLED` | 多 Agent 评测 | false |

### 15.3 术语表

- **Harness**：围绕 Agent 的运行时脚手架，负责上下文、工具、状态、恢复、审计。
- **Checkpointer**：LangGraph 的图状态持久化组件；按 `thread_id` 存取。
- **Hot/Cold tier**：Redis 热层 / Postgres 冷层。
- **Consolidation**：把多条 episodic 记忆合并成 semantic 记忆。
- **PEL**：Redis Stream 的 pending entries list，记录已投递未 ack 的消息。
- **XAUTOCLAIM**：认领其他消费者长时间未 ack 的消息。
- **SSE**：Server-Sent Events，HTTP 单向事件流。
- **Last-Event-ID**：SSE 重连时客户端上报的最后事件 id。
- **BM25**：基于词频/逆文档频率的检索算法。
- **Ebbinghaus decay**：按时间衰减记忆强度的公式。
- **Specialist**：外部 CLI Agent（pi/codex/claude）。
- **Subagent**：Engram 自己的 leaf 副本。
- **Skill**：提示词层面的过程知识包。
- **VersionDAG**：演化产物的版本图 + `is_active` 单指针 + 回滚。

### 15.4 推荐阅读顺序（源码）

1. `app/bootstrap.py` → `leader/factory.py` → `leader/agent.py`
2. `app/gateway/chat.py` → `app/services/stream_service.py` → `app/gateway/sse_buffer.py`
3. `context_engineering/strategies/default/strategy.py` → `budget.py` → `externalizer.py` → `summarizer.py`
4. `memory/adapters/tiered_store.py` → `redis_store.py` → `pg_store.py` → `strategies/default/retriever.py`
5. `memory/stream_queue.py` → `worker.py` → `consolidation_worker.py`
6. `runtime/pg_checkpointer.py` → `run_manager.py` → `journal/run_journal.py` → `runtime/pg_run_store.py`
7. `sandbox/sandbox.py` → `local/local_sandbox_provider.py` → `guards/local_security_guard.py`
8. `mcp/loader.py` → `registry.py` → `guards/`
9. `multiagent/bootstrap.py` → `skill/selector.py` → `skill/injector.py`

### 15.5 检查清单

- [ ] 能不看资料讲顺一条请求：session → run → graph → middleware → model/tool → SSE → artifacts。
- [ ] 能说清 checkpointer / memory / run artifact 三者的区别。
- [ ] 能说清冷先写、热先读、冷命中回填的原因。
- [ ] 能说清 Stream 的 at-least-once、PEL、XAUTOCLAIM。
- [ ] 能说清 SSE 的 `id:` / `Last-Event-ID` / 500 帧缓冲 / dropped header。
- [ ] 能说清 P1/P4/P5 的触发条件与动作。
- [ ] 能说清本地沙箱为什么不是隔离。
- [ ] 能说清 Skill 与 Tool 的区别。
- [ ] 能说清 2,764 个测试证明/不证明什么。
- [ ] 能说出至少三个当前边界与对应改进方向。

---

*文档版本：2026-11-15 · 基于 `main` 分支 27 个 commit · 测试实测 2764 passed / 12 skipped / 90.20s*