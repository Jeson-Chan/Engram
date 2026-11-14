# Engram 面试叙事要点（话术弹药）

> 每个讲点：一句话结论 + 追问纵深。按被问到的深度取用。

## 1. 为什么网关绝不走 sync 入口（LeaderAgent.run）

**一句话**：`LeaderAgent.run` 内部 `asyncio.run(...)`——在有事件循环的 ASGI
worker 里再嵌套 run 会直接抛 `RuntimeError: cannot be called from a running
event loop`；这不是"会慢"，是**根本跑不起来**。

**纵深**：
- 网关直接包装 `EngramStreamClient`（`graph.astream` 异步生成器），token 级
  delta 逐帧转发——顺带拿到流式（不是牺牲，是白赚）
- 流路径上所有阻塞 IO（`RunJournal` JSONL 追加、run 状态转移、报告落盘）
  全部 `asyncio.to_thread`——事件循环零阻塞，事件流不冻结
- 沙箱 acquire 这类重阻塞发生在 graph 工具执行内部（LangGraph 已把它们
  放进 executor），网关层天然碰不到

## 2. 记忆分层存储的取舍

**一句话**：热层（Redis）管"快与淘汰"，冷层（Postgres）管"全量与兜底"——
写路径冷先沉淀（持久性保证），读路径热 miss 落冷并回填（淘汰的记忆被
再次想起时重新变热）。

**纵深（追问"为什么不向量库/为什么不只有 Redis"）**：
- 分区键 `engram:mem:{user}:{thread}:{trace_id}`——会话状态隔离的作用域键
  与 graph checkpointer 的 thread_id 同构，一套心智模型
- TTL 语义：落键即带 TTL（redis-cli 可见倒计时），读命中刷新——"常被想起
  的记忆保持热，久不想起的自然冷却"——认知科学隐喻即工程语义
- 冷层 JSONB 与热层共用同一序列化器——两层说同一种话，Tiered 组合零转换
- 迁移 expand-contract：Markdown 旧库先并行（迁移脚本幂等导入），全量入冷
  后旧路径退役——不是一刀切的大爆炸切换

## 3. Redis Stream 巩固队列（为什么不是 pub/sub、不是 list）

**一句话**：巩固要 **at-least-once**——pub/sub 断线即丢、list 无消费位点；
Stream 的消费者组三件套（last-delivered-id 偏移量、PEL pending、XAUTOCLAIM
认领）天然实现"不丢不重（可容忍重）"。

**纵深**：
- 失败不 `XACK` → 消息留 PEL → 下一轮 `XAUTOCLAIM` 认领重放；
  `min-idle-time` 阈值防抢正在处理的消息（活消费者不被干扰）
- 重复处理被 `encode` 的 `MemoryConflictError` 幂等吸收——业务层兜住
  at-least-once 的"可重"
- Web 重启不丢事件：事件 `XADD` 即持久在 Stream，消费可以晚到
- 消费者组 = 多 worker 水平扩展不加代码；组偏移量在 Redis 侧——
  消费者无状态、随便杀
- 毒丸防护：载荷损坏的消息直接 ack（否则永久重放卡死队列）

## 4. SSE 断线续传与 Stream 是同一套语义（讲点一致性）

**一句话**：SSE 规范的 `id:` 行 + `Last-Event-ID` 头 = 客户端持有的偏移量；
服务端缓冲缺口重放 = PEL pending 重放——两张脸，一个心智模型。

| | Redis Stream 巩固队列 | SSE 网关 |
|---|---|---|
| 偏移量 | group last-delivered-id | Last-Event-ID（客户端持有序号）|
| 断点重放 | PEL + XAUTOCLAIM | per-session 环形缓冲补发 |
| 语义 | at-least-once | at-least-once（客户端按 id 幂等）|

**追问兜底**：超缓冲容量的缺口无法补——流内 error 事件 +
`X-Engram-Events-Dropped` 头明示，客户端决定重开会话（诚实降级，
不装作没丢）。

## 5. PG checkpointer：多 worker 从架构上成立

**一句话**：LangGraph 会话状态从进程内单例换 `AsyncPostgresSaver`
（连接池）——重启读回同一会话；两个 uvicorn worker 各持独立池、共享
同一 PG 状态表——水平扩展不是"配置出来的"，是**存储模型决定的**。

**追问兜底**：装配时机在 lifespan 且**先于** bootstrap——graph 编译时
checkpointer 已就位；不配 DSN 回退 InMemorySaver，CLI 本地行为零变化。

## 6. 测试哲学（被问"2800 个测试怎么维护"）

**一句话**：外部行为测试——HTTP 语义、SSE 帧序列、Stream 组语义；
内部全靠注入缝（runtime_factory / store / graph fake），测试永不碰真实
provider 与网络。

**纵深**：CI 挂 postgres/redis service container，live 测试真跑（恢复/
重放/兜底语义实测）；本地无依赖时显式 skip——诚实的测试边界，不靠
mock 骗绿。

## 7. 项目里修过的真 bug（展示深度的工作证据）

- 上游模板重写丢了 `${messages_text}` 占位符——压缩 prompt 不带对话
  历史就发 LLM（**测试过时≠代码对**，逐一判定的典型案例）
- `asyncio.to_thread` cancel 不传播到工作线程——孤儿线程与测试抢锁的
  时序 flaky（全量绿、单独红的诡异形态，根因是调度竞争）
- "Windows 环境性失败" 10 个——真凶是一个测试改 `os.environ["PATH"]`
  不还原污染全会话（环境性失败的**误诊**案例）
- psycopg `execute()` 拒绝多语句 DDL；Windows ProactorEventLoop 不兼容
  psycopg async（`loop_factory=SelectorEventLoop`）
