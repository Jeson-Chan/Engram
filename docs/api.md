# Gateway HTTP API 参考

网关（`python -m engram.backend.app.gateway`，默认 `127.0.0.1:8000`）的全部端点、错误码与 curl 示例。SSE 事件语义（answer/tool/thinking/skill/budget/sandbox/error/done 与断线续传）见 `docs/event-semantics.md`；运行时缺陷底账见 `docs/e2e-baseline.md`。

交互式文档：启动网关后打开 `http://127.0.0.1:8000/docs`。

## 端点一览

| 方法 | 路径 | 说明 | 依赖 |
|---|---|---|---|
| POST | `/sessions` | 新建会话（独立 thread_id） | — |
| GET | `/sessions?user_id=` | 会话列表（可按用户过滤） | 会话库（默认 SQLite） |
| GET | `/sessions/{id}` | 会话详情 | — |
| DELETE | `/sessions/{id}` | 删除会话（404 幂等） | — |
| POST | `/sessions/{id}/chat` | SSE 流式对话 | runtime |
| POST | `/sessions/{id}/research` | SSE 流式研究（run 进 PG 历史） | runtime |
| GET | `/sessions/{id}/runs` | 会话运行历史 | PG（`ENGRAM_RUNS_PG_DSN`） |
| GET | `/runs/{run_id}/report` | 运行报告（Markdown） | PG + 产物在盘 |
| GET | `/sessions/{id}/messages` | 历史消息回放（checkpointer） | runtime + checkpointer |
| GET | `/memory/stats` | 记忆统计（hot/cold/forgotten/consolidation） | 记忆层（`ENGRAM_MEMORY_USE`） |
| GET | `/memory/traces` | 记忆列表（过滤 + 层标注） | 记忆层 |
| GET | `/runs/{run_id}/events` | Run 事件时间线（持久日志） | runtime |
| GET | `/status` | 客户端状态（模型/模式/能力） | runtime |
| GET | `/app` | Web 工作台（SPA，`ENGRAM_WEB_UI_ENABLED`） | 构建产物 `web/dist` |

## 查询参数

- `GET /sessions/{id}/messages`：`limit`（默认 50，≤500）、`offset`（≥0）；返回 `MessageView` 列表（时间正序窗口）。
- `GET /memory/traces`：`user_id`、`q`（子串）、`type`（episodic/semantic/procedural）、`min_strength`、`forgotten`、`layer`（hot/cold）、`limit`（默认 100，≤500）。
- `GET /memory/stats`：`user_id`。
- `GET /runs/{id}/events`：`limit`（默认 200，≤2000）、`offset`。

## 错误码表

| 状态码 | 场景 | 语义 |
|---|---|---|
| 404 | session/run 不存在 | 资源未找到；删除已删会话幂等 404 |
| 410 | `/runs/{id}/report` | 报告产物已不在磁盘 |
| 422 | 请求体校验失败 | 参数缺失/类型不符 |
| 503 | `agent runtime not ready` | runtime 未完成 bootstrap（`/chat`、`/research`、`/messages`、`/runs/{id}/events`、`/status`） |
| 503 | `run history requires PG (ENGRAM_RUNS_PG_DSN)` | 运行历史端点未配 PG |
| 503 | `memory not configured (set ENGRAM_MEMORY_USE and Redis/PG)` | 记忆端点未启用记忆层 |
| 503 | `checkpointer unavailable` | `PG 断连等持久层故障（/messages） |
| 503 | `run journal unreadable` | 事件日志读失败 |

SSE 流内错误不改变 HTTP 状态（200 开流）：流内以 `error` 事件 + `done` 收尾（见 `docs/event-semantics.md`）。

## curl 示例

以下示例可按顺序实际执行（`SID` 为第一个命令返回的 `session_id`）：

```bash
# 1. 新建会话
curl -s -X POST localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "demo-user", "metadata": {"title": "记忆研究"}}'
# → {"session_id":"...","thread_id":"thread-...","user_id":"demo-user",...}

SID=<上一步的 session_id>

# 2. 会话列表 / 详情
curl -s "localhost:8000/sessions?user_id=demo-user"
curl -s "localhost:8000/sessions/$SID"

# 3. SSE 流式对话（-N 关闭缓冲；事件语义见 docs/event-semantics.md）
curl -N -X POST "localhost:8000/sessions/$SID/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 4. SSE 流式研究
curl -N -X POST "localhost:8000/sessions/$SID/research" \
  -H "Content-Type: application/json" \
  -d '{"message": "研究 LangGraph 的记忆分层"}'

# 5. 历史消息回放（多轮对话后）
curl -s "localhost:8000/sessions/$SID/messages?limit=50"

# 6. 运行历史 + 单次 Run 事件时间线 + 报告
curl -s "localhost:8000/sessions/$SID/runs"
RUN=<运行历史里任一 run_id>
curl -s "localhost:8000/runs/$RUN/events?limit=200"
curl -s "localhost:8000/runs/$RUN/report"

# 7. 记忆统计与检索（配置记忆层后）
curl -s "localhost:8000/memory/stats?user_id=demo-user"
curl -s "localhost:8000/memory/traces?user_id=demo-user&q=%E8%AE%B0%E5%BF%86&type=semantic"

# 8. 客户端状态（无密钥）
curl -s "localhost:8000/status"

# 9. Web 工作台（ENGRAM_WEB_UI_ENABLED=true 且已构建 web/dist）
curl -s "localhost:8000/app"

# 10. 删除会话（幂等 404）
curl -s -X DELETE "localhost:8000/sessions/$SID" -o /dev/null -w "%{http_code}\n"
curl -s -X DELETE "localhost:8000/sessions/$SID" -o /dev/null -w "%{http_code}\n"
```

## 会话持久化

会话映射默认落 SQLite `.engram/gateway.db`（WAL）——网关重启后 `GET /sessions` 仍返回旧会话，`session_id` 仍可解析到原 `thread_id`。环境变量 `ENGRAM_GATEWAY_DB` 可覆盖路径；设为 `memory` 显式退回纯内存（重启即丢，不推荐）。

## Web 工作台

`ENGRAM_WEB_UI_ENABLED=true`（默认 false）且 `web/dist`（或 `ENGRAM_WEB_UI_DIST`）存在时：`/app` 返回 SPA，`/app/*` 未知前端路由回退 `index.html`（history 路由由前端接管），静态资源挂 `/app/assets`。关闭或产物缺失时零 web 路由注册，网关行为不变。

## Windows 注意

Windows 上必须用 `python -m engram.backend.app.gateway` 启动（强制 `WindowsSelectorEventLoopPolicy`——异步 Postgres 驱动的要求）；裸 `uvicorn ...:app` 会以 Proactor 循环启动，配置 PG DSN 后启动失败（见 `docs/e2e-baseline.md` 缺陷 A）。
