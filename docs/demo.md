# Engram 演示脚本（两幕 + Web 工作台）

> 全程 curl 可照走。前置：`docker compose up`（agent + redis + postgres），
> 网关默认监听 `http://localhost:8000`（容器内 uvicorn）。本地裸跑见文末备选。

---

## 零幕（推荐）：一键演示 + Web 工作台

```bash
# 一键：起 PG/Redis → 幂等 seed（固定会话/记忆/run/报告）→ 网关 + Web UI
python scripts/demo.py
# → 打开 http://127.0.0.1:8000/app（ENGRAM_WEB_UI_ENABLED 已置）
# 清理 demo 数据（只删 seed 标记的数据）：
python scripts/demo.py --clean
```

Web 工作台 5 分钟脚本（seed 的「上周的 LangGraph 记忆研究」会话已就绪，
不依赖现场生成、不依赖外网搜索——环境限制见 `docs/e2e-baseline.md`）：

1. 打开 `/app` → 左栏选「上周的 LangGraph 记忆研究」（历史/记忆/run 预置）。
2. Run Inspector：最近 run 的时间线 + 报告预览/下载；工具节点与对话区工具卡片互相定位。
3. Memory Explorer：热层/冷层/遗忘/巩固计数；按类型/强度/层筛选，看强度条。
4. 现场流式研究：输入「分层记忆怎么实现？」→ token 级流式 + 工具卡片 + 召回提示展开。
5. 刷新页面 → 会话/历史消息/最近 run 恢复（SQLite 会话映射 + checkpointer）；
   流中途断线 → 重连带 `Last-Event-ID` 补发，缺口超限显式提示。
6. TUI 驾驶舱（另开终端 `engram`）：`Ctrl+K` 切会话 / `Ctrl+O` Run 时间线 /
   `Ctrl+G` Memory / `Ctrl+U` Inspector / `Esc` 关闭任何弹层。

API 细节见 `docs/api.md`；SSE 事件语义见 `docs/event-semantics.md`。

---

## 主幕：跨会话记忆 —— "隔一周回来，agent 还记得研究到哪"

**叙事**：用户周一研究了一个课题，聊了十几轮；一周后回来接着聊——
agent 不仅记得结论（冷层沉淀兜底），高频要点还在热层秒回。

### Step 1 —— 起会话，聊研究课题

```bash
# 创建会话（记住 session_id）
curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "demo", "metadata": {"topic": "sse-resume"}}'
# → {"session_id": "9f2a...", "thread_id": "thread-20261114T...", ...}

SID=<上面的 session_id>

# 聊几轮（SSE 流式；-N 关缓冲实时看）
curl -N -X POST http://localhost:8000/sessions/$SID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我在研究 SSE 断线重连，已确认用 Last-Event-ID 方案，还差事件缓冲设计"}'
```

### Step 2 —— 让记忆落层（巩固是异步的，等一轮）

记忆抽取/巩固在后台 Stream 消费者跑（at-least-once）。
Redis 热层键已分区落位——redis-cli 直接可见：

```bash
docker compose exec redis redis-cli --scan --pattern 'engram:mem:*' | head
# 键形如 engram:mem:demo:thread-20261114T...:<trace_id>
docker compose exec redis redis-cli TTL engram:mem:demo:thread-...:<trace_id>
# → TTL 倒计时（热记忆随时间淘汰；检索命中会续命）
```

PG 冷层是全量沉淀：

```bash
docker compose exec postgres psql -U engram -d engram -c "SELECT count(*) FROM memory_traces"
```

### Step 3 —— "一周后"回来：FLUSH 热层模拟失忆，验证冷层兜底

```bash
# 模拟热层全失忆（TTL 到期 / 重启丢缓存）
docker compose exec redis redis-cli FLUSHDB

# 同一会话继续聊——记忆从冷层召回并回填热层（流里可见 recalled 上下文生效）
curl -N -X POST http://localhost:8000/sessions/$SID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "继续上次的研究——事件缓冲设计定了吗？"}'
```

**演示点**：热层空了，agent 依然记得研究方向与结论——冷层兜底 + 召回回填。
（对照测试：`tests/v1/unit/memory/test_tiered_store.py::test_live_flush_hot_recall_from_cold`）

### Step 4 —— 服务重启会话不失忆（PG checkpointer）

```bash
docker compose restart agent   # LangGraph 会话状态在 PG
curl -N -X POST http://localhost:8000/sessions/$SID/chat \
  -H "Content-Type: application/json" -d '{"message": "我们聊到哪了？"}'
```

**演示点**：同一 thread_id 的 graph state 从 PG 读回——"重启不失忆"。

---

## 辅幕：流式研究 —— "提交问题 → 流式吐报告"

### Step 1 —— 提交研究问题，看流实时吐

```bash
curl -N -X POST http://localhost:8000/sessions/$SID/research \
  -H "Content-Type: application/json" \
  -d '{"message": "Redis Stream 消费者组如何保证 at-least-once？"}'
# event: thinking → answer → tool_start/tool_end → done（帧帧实时）
```

### Step 2 —— 弱网断线重连（Last-Event-ID 补齐）

```bash
# 掐断重连：带 Last-Event-ID（上一帧的 id: 行）——缺口事件先补发再接续
curl -N -X POST http://localhost:8000/sessions/$SID/chat \
  -H "Content-Type: application/json" -H "Last-Event-ID: 5" \
  -d '{"message": "Q"}'
# id: 6,7,8...（缓冲缺口补发）→ 新流
```

### Step 3 —— 回顾历史与报告

```bash
# 该会话的运行历史（PG 落库：状态/时间线/报告引用）
curl -s http://localhost:8000/sessions/$SID/runs
# 取某次运行的最终报告（markdown 产物）
curl -s http://localhost:8000/runs/<run_id>/report
```

---

## 深度演示（面试追问）：Stream 巩固队列的重放

```bash
# 看队列与消费者组
docker compose exec redis redis-cli XLEN engram:mem:consolidate
docker compose exec redis redis-cli XINFO GROUPS engram:mem:consolidate
# pending（孤儿消息——消费者崩溃残留，重启后 XAUTOCLAIM 认领重放）
docker compose exec redis redis-cli XPENDING engram:mem:consolidate consolidators

# 杀掉 worker 再起（待处理事件重放不丢）
docker compose stop consolidation-worker && docker compose up -d consolidation-worker
```

**演示点**：杀消费者 → PEL 里孤儿可见 → 重启认领重放 → 全部 ack（PEL 归零）。
（对照测试：`tests/v1/unit/memory/test_stream_queue.py::test_killed_consumer_replays_pending`）

---

## 本地裸跑备选（不起 docker）

```bash
pip install -e ".[dev]"
# 依赖：redis + postgres 本地实例（或只测内存路径——不配 ENGRAM_REDIS_URL 即回退）
ENGRAM_REDIS_URL=redis://localhost:6379/0 \
ENGRAM_MEMORY_PG_DSN=postgresql://engram:engram@localhost:5432/engram \
ENGRAM_CHECKPOINT_DSN=postgresql://engram:engram@localhost:5432/engram \
python -m engram.backend.app.gateway --port 8000
```

> 注（E2E 缺陷 A 修复后的正确姿势）：Windows 上必须用
> `python -m engram.backend.app.gateway` 启动（强制 `WindowsSelectorEventLoopPolicy`，
> psycopg async 要求）；裸 `uvicorn ...:app` 会以 Proactor 循环启动，
> 配置 PG DSN 后启动失败。macOS/Linux 两种入口都可用。
