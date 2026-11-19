# E2E 基线（2026-11-16）

本文件是 2026-11-16 全功能端到端测试的缺陷基线，作为 OpenSpec change `web-tui-research-workbench` 的修复追踪底账。完整测试过程、复现命令与原始证据见 `.scratch/engram-e2e-2026-11-16/report.md`（仓库外工作目录）。

- 被测版本：`d96ebf1`
- 环境：Windows 11 / Python 3.12.8 / uvicorn 0.54 / LangGraph 1.x，Docker Compose 起 PG 16 + Redis 7
- 自动化检查：68/73 通过；单元/集成测试 2764 passed, 12 skipped

## 缺陷清单与处置

| # | 优先级 | 缺陷 | 状态 | 处置 |
|---|---|---|---|---|
| A | 高 | Windows + PG：uvicorn 0.54 默认 Proactor 循环，psycopg 异步拒绝，网关启动失败 | 已修复 | `runtime-hardening` / Windows 与 Postgres 启动（任务 2.1） |
| B | 高 | `delegate_to_subagent` 调用不存在的 `LeaderAgent.invoke`，真实运行时 100% 失败 | 已修复 | `runtime-hardening` / 内部 subagent 委托（任务 2.2） |
| C | 高/隐私 | 长期记忆不按用户隔离：Bob 能召回 Alice 的私有记忆 | 已修复 | `runtime-hardening` / 记忆用户与线程隔离（任务 2.3） |
| D | 中 | 记忆线程归属全部为 `unknown`（Redis 键 `engram:mem:default:unknown:<id>`） | 已修复 | `runtime-hardening` / 记忆线程归属（任务 2.4） |
| E | 中 | Redis Stream 巩固 worker 因局部导入 `NameError` 静默降级为进程内队列 | 已修复 | `runtime-hardening` / Redis Stream 巩固队列（任务 2.5） |
| F | 中 | HTTP session_id 不跨网关重启持久化（`SessionRegistry` 纯内存） | 已修复 | `gateway-client-api` / 会话持久化（任务 4.1） |
| G | 中 | `/chat` 运行不进入 PG 运行历史；断连状态不可见 | 已修复 | `runtime-hardening` / Chat 运行历史（任务 3.1） |
| H | 低 | TUI 弹层（命令面板/MCP）输入框聚焦时 Esc 关不掉 | 已修复 | `tui-research-cockpit` / 键盘优先操作（任务 6.4） |
| I | 低/前向兼容 | LangGraph checkpoint 反序列化 `AgentError` 未注册类型告警 | 已修复 | `runtime-hardening` / Checkpoint 兼容性（任务 3.2） |
| J | 环境限制 | 内置 `web_search` 在当前网络无结果（DuckDuckGo 不可达） | 环境限制 | 非目标：不修复网络；演示不依赖外网搜索（任务 3.3 记录规避） |
| K | 环境限制 | Docker sandbox（`agent-sandbox` / 镜像）未安装，仅验证 LocalSandbox | 环境限制 | 非目标：proposal 明确不做 Docker sandbox |
| L | 环境限制 | 仅 `OPENAI_API_KEY` 可用，其它 Provider 无法真实切换测试 | 环境限制 | 非目标：不做 Provider 切换 UI；外部专家缺失按设计优雅失败 |

## 状态说明

- **待修复**：对应本 change 的 requirement，修复后本表更新为「已修复」并附回归测试入口。
- **环境限制**：当前测试环境不可用，非代码缺陷；演示脚本与 README 需明确不依赖这些能力。
- 已验证通过的能力（会话 CRUD、SSE 流式与断线续传、本地沙箱、MCP、Skill、冷热层召回、CLI/TUI 主链路）不在此重复，详见 E2E 报告第 4 节。

## 修复记录

- **A（Windows + PG 启动）已修复**：新增 `engram/backend/app/gateway/entry.py`（推荐入口 `python -m engram.backend.app.gateway`：win32 强制 Selector 策略 + `uvicorn.run(loop="none")`）与 lifespan 快速失败自检 `assert_loop_compatible_for_pg()`（win32 + Proactor + PG DSN → 秒级 RuntimeError + 可操作提示，替代 30 秒 PoolTimeout）。回归：`engram/backend/tests/v1/unit/gateway/test_loop_selection.py`（9 tests）。README（en/zh/ja）Windows 快速开始已改用新入口。
- **B（内部 subagent）已修复**：`LeaderAgent.invoke(state, config)` 同步兼容入口（委托 `graph.ainvoke`——MCP async-only 工具要求；无循环→asyncio.run，循环内→独立线程新循环；缺省自动生成隔离 thread_id 供 checkpointer）。回归：`engram/backend/tests/v1/unit/multiagent/test_subagent_real_leader.py`（真实 `make_lead_agent` 编译 graph，4 tests；旧测试用 MagicMock 假 agent 正是漏测原因）。
- **C（记忆用户隔离）+ D（线程归属）已修复**：`MemoryQuery.user_id/thread_id`（retriever 按用户过滤，旧数据视为 `default` 仍可读，CLI 无 user 路径不变）；`MemoryTask.user_id` → encode 归属 metadata；`_compute_trace_id` 纳入 user（同内容跨用户不撞 id）；consolidate 候选按用户过滤 + 合并产物继承归属；两个 middleware 改用 `langgraph.config.get_config()`（旧 `getattr(runtime, "config")` 永远 None → `unknown` 根因）；网关 chat/research config 透传 `ctx.user_id`。回归：`engram/backend/tests/v1/unit/memory/test_user_thread_isolation.py`（17 tests：Alice/Bob 隔离、旧数据可读、真实 Runtime、fakeredis 分区键、真实 worker+retriever 端到端）。
- **E（Stream 巩固队列）已修复**：`StreamConsolidationQueue/Consumer` 导入提升到 `memory/bootstrap.py` 模块级（原在 `_build_worker` 函数内局部导入，`_StreamModeWorker.__init__` 在全局作用域查名必然 NameError → 静默降级）；降级路径改为明确的 warning（含 "events will NOT survive a restart" 提示）；Stream 事件载荷补齐 `user_id` 序列化（缺陷 C 的 Stream 路径）。回归：`engram/backend/tests/v1/unit/memory/test_stream_worker_mode.py`（6 tests：fakeredis 下 `_build_worker` 返回 Stream 模式、XADD/消费/ack 全链路、失败留 PEL、降级可见）。
- **G（Chat 运行历史）已修复**：抽出 `engram/backend/app/gateway/run_projection.py`（chat/research 共用 RunProjection，best-effort：投影失败不断流、不翻转终态）；chat 在 start/success/failure/client-disconnect 四个转移点写 PGRunStore；research 的断连分支也补投影（同步 best-effort，CancelledError 分支不能 await）。回归：`engram/backend/tests/v1/unit/gateway/test_chat_run_history.py`（5 tests：成功→success、流内异常→error+原因、断连→error+断连原因、无 PG no-op、投影故障不外抛）。
- **F（会话持久化）已修复**：`SessionStore`（SQLite `.engram/gateway.db` WAL 默认，`ENGRAM_GATEWAY_DB` 可覆盖/`=memory` 显式不落盘）；`SessionRegistry` 注入 store（create/delete 落盘、构造回灌）。回归：`engram/backend/tests/v1/unit/gateway/test_session_store.py`（两个 app 共享同一 db 文件的重启语义等 12 tests）；tests 根 conftest 对 `ENGRAM_GATEWAY_DB` 做每测试隔离。

## 最终验证（2026-11-17，任务 7.5）

| 检查 | 结果 |
|---|---|
| pytest 全量（`engram/backend/tests`） | ✅ **2881 passed, 12 skipped**（改动前基线 2764；新增 43 个回归测试；live PG/Redis 测试按 `ENGRAM_TEST_PG_DSN` 未配置而 skip） |
| 前端单测（Vitest，`web/`） | ✅ 14/14（SSE 契约直接解析本文档同源 `docs/event-semantics.md` + 三栏壳组件） |
| 前端构建 | ✅ `tsc -b && vite build`（产物挂载 `/app` 验证 200） |
| Playwright smoke（真实网关 + 真实 LLM） | ✅ 2/2（desktop 57.9s / narrow 1.2m：新建会话→流式回答→Memory 展开→刷新恢复会话/历史；用系统 Edge 通道） |
| 演示叙事演练（任务 7.3，live） | ✅ 清 Redis 热层 → stats 显示 cold=5 兜底 → 一轮真实对话回答原文引用 seed 记忆（BM25 复合分、Ebbinghaus 衰减）→ 召回回填热层（hot 0→1）→ 重启网关 → 会话完整恢复（SQLite） |
| 一键演示脚本 | ✅ `python scripts/demo.py` 全流程（compose 冲突自动回退 docker start → 幂等 seed → 网关 + Web UI → 5 分钟脚本横幅；该脚本已随 demo 板块移除，历史提交可查） |

过程中现场复核的缺陷行为：中途刷新打断流 → run 记 `error(client disconnected)` 并进 PG 历史（缺陷 G 修复的活体验证）；`--clean` 只删 demo 标记数据（PG/Redis/SQLite/产物目录全清零，非 demo 数据不动）。

测试环境备注：仓库根存在真实 `.env`（演示用）时，`gateway.main` 导入期 `load_dotenv` 会串扰测试进程 → tests 根 conftest 剥离运行时环境键（密封基线）。本机 8000 端口若被其它进程占用，用 `ENGRAM_DEMO_PORT` 覆盖演示端口。

## 环境限制与演示规避

- **DuckDuckGo 不可达**：`web_search` 在当前网络返回 `No results found`（绕过 Engram 直连 `ddgs` 同样失败，确认非本仓库缺陷）。演示叙事不依赖外网搜索；research 演示使用预置记忆与本地沙箱（见任务 7.1 seed）。
- **仅 OpenAI Key**：`.env` 只有 `OPENAI_API_KEY`（实际模型 `deepseek-v4.1-flash-1017`）。演示与 seed 全部走该 provider；不现场切换 provider。
- **Docker sandbox 依赖缺失**：`agent-sandbox` 未安装、`all-in-one-sandbox:latest` 镜像不存在。演示使用 `LocalSandboxProvider`（`ENGRAM_SANDBOX_USE=engram.backend.agents.sandbox.local.local_sandbox_provider:LocalSandboxProvider`）。
