<div align="center">

<!-- IMAGE SLOT: hero banner (insert here — e.g. docs/assets/hero.png) -->

# Engram

**A deep research agent with long-term memory — served over HTTP.**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-SSE-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-Streams-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-checkpointer-4169E1?style=for-the-badge)](https://www.postgresql.org/)

Animated wordmark: [logo/standalone.html](logo/standalone.html) — letters as memory cells, a glint sweeping across: a memory being recalled.

[English](#english) · [简体中文](#中文) · [日本語](#日本語)

</div>

---

## 中文

### 这是一个什么

Engram 是一个**深度研究 agent**：ReAct 内核、middleware 优先架构、五层长期记忆、沙箱隔离、技能自进化——并把它**封装成一个长期运行的服务**：

- **FastAPI 网关**：会话管理、SSE 流式对话/研究、运行历史查询、Swagger
- **长期记忆分层存储**：Redis 热层（按 user/thread 分区、TTL 淘汰、读刷新）兜底 Postgres 冷层（全量沉淀）——热层清空也不会失忆
- **会话状态持久化**：LangGraph checkpointer 落 Postgres，重启服务会话继续，多 worker 共享同一会话状态
- **记忆巩固队列**：Redis Stream 消费者组，at-least-once（偏移量续传 + PEL 重放），独立 worker 进程可水平扩展

同一个二进制也保留了本地交互形态：全屏 TUI / CLI。内核与服务共用一套代码。

**2764 个测试**守护内核与服务；恢复/重放/兜底相关的套件在 CI 里对真实 Redis + Postgres 容器实跑。

### 用来做什么

- **长期研究服务**：用户提交问题，SSE 流式吐出推理、工具调用与最终报告；断线重连不丢帧
- **跨会话记忆**：agent 记得此前的会话。把整个 Redis 热层清空（`FLUSHDB`），Postgres 冷层仍能召回——被淘汰的记忆在召回时重新变热
- **agent 工程化的参考实现**：只为异步的网关（绝不触碰 `asyncio.run` 同步入口）、两层存储、Stream 消费组重放、与 Stream 同构的 SSE 续传语义

### 演示 Demo

**第一幕：跨会话记忆。** 清空整个热层（"把近期记忆全部忘掉"），agent 依然接得上此前的讨论——冷层作答，召回的记忆回填热层：

```bash
# 清空热层（模拟缓存失效 / TTL 到期）
docker compose exec redis redis-cli FLUSHDB

# 同一会话继续聊 → 冷层兜底召回
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "继续上次的研究——缓冲设计定了吗？"}'
```

**第二幕：流式研究 + 断线重连。** 提交研究问题，事件流实时吐出；连接中断后带上最后一帧的 id 重连，缺口事件先补发、再接续实时流：

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking / answer / tool_start / tool_end / done

# 断线重连：带上一帧的 id 行
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# id: 6, 7, 8 ...（缓冲缺口补发）→ 接续实时流
```

<!-- IMAGE SLOT: demo screenshot / asciinema GIF (insert here) -->

完整可照走的演示脚本（两幕 + `redis-cli` 杀消费者看重放）：[docs/demo.md](docs/demo.md)

### 安装 Installation

**前置条件**

- Python **3.12+**
- 一个 LLM API key（默认 `DEEPSEEK_API_KEY`，也兼容任何 OpenAI 兼容 provider）
- Docker（仅全栈路径需要；本地路径零依赖）

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows（Linux/macOS：source .venv/bin/activate）
pip install -e ".[dev]"
cp .env.example .env                 # 填入 DEEPSEEK_API_KEY=sk-xxx
```

### 快速开始 Quick Start

**服务模式（30 秒看到第一个流）：**

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000

# 新终端：
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "研究：SSE 断线重连的主流方案"}'
```

预期输出（SSE 帧）：

```text
event: thinking   data: {"type": "thinking", "content": "…"}    ← 推理 delta
event: answer     data: {"type": "answer",   "content": "…"}    ← 回答 token
event: tool_start data: {"type": "tool_start", "tool_name": "…"} ← 工具调用
event: done       data: {"type": "done"}                         ← 总是以 done 终止
```

浏览器打开 **http://localhost:8000/docs**（Swagger 即兴试 API）；研究跑完后取历史与报告：

```bash
curl -s localhost:8000/sessions/$SID/runs       # 运行历史
curl -s localhost:8000/runs/<run_id>/report     # 最终报告（markdown）
```

**本地交互模式：** 直接运行 `engram` 进入全屏 TUI；输入问题开始研究，`/` 触发命令补全。

### Docker 支持 Docker Support

```bash
cp .env.example .env     # 填入 DEEPSEEK_API_KEY
docker compose up -d     # 网关 + Postgres + Redis + 巩固 worker
```

| 服务 | 作用 | 端口 |
|---|---|---|
| `gateway` | FastAPI + SSE 网关（会话/对话/研究/历史 + Swagger） | **8000** |
| `postgres` | 会话状态 checkpointer + 记忆冷层 + 运行历史 | 5432 |
| `redis` | 记忆热层 + 巩固队列 Stream | 6379 |
| `consolidation-worker` | 独立巩固消费者（与网关内联消费者同组） | — |
| `agent` | 本地 TUI（`tui` profile，按需） | — |

- 依赖接线全自动：网关通过环境变量拿到 `ENGRAM_CHECKPOINT_DSN` / `ENGRAM_REDIS_URL` / `ENGRAM_MEMORY_PG_DSN`，无需手工配置
- 数据卷：`.engram/pgdata`（Postgres）、`.engram/redisdata`（Redis）、`.engram/`（运行时 journal/artifacts）、`skills/`
- TUI 交互：`docker compose run --rm agent`（首次会触发配置向导）
- Docker 沙箱隔离：按 `docker-compose.yml` 注释取消 `docker.sock` 挂载并设置 `ENGRAM_SANDBOX_USE`

更多配置、命令与排错：[Usage Guide](USAGE.md)

---

## English

### What is this

Engram is a **deep research agent** — a ReAct kernel with middleware-first architecture, five-layer long-term memory, sandbox isolation and skill evolution — **packaged as a long-running service**:

- **FastAPI gateway**: session management, SSE-streaming chat / research, run history, Swagger
- **Tiered long-term memory**: a Redis hot tier (per user/thread partitioned keys, TTL eviction, read-refresh) over a Postgres cold tier (full sediment) — wiping the hot tier does not cause amnesia
- **Session-state persistence**: a LangGraph checkpointer on Postgres; restart the service and sessions continue, multiple workers share the same session state
- **Consolidation queue**: a Redis Stream consumer group, at-least-once (offset resume + PEL replay), with a standalone worker process that scales horizontally

One binary, two faces: the same kernel also runs locally as a full-screen TUI / CLI.

**2764 tests** guard the kernel and the service; the recovery / replay / fallback suites run live against real Redis + Postgres service containers in CI.

### What is this for

- **A long-running research service**: submit a question and stream reasoning, tool calls and the final report over SSE; reconnect without losing frames
- **Cross-session memory**: the agent remembers earlier sessions. Wipe the entire Redis hot tier (`FLUSHDB`) and the Postgres cold tier still answers — evicted memories are re-warmed on recall
- **A reference implementation** of the engineering around an agent: an async-only gateway (never the `asyncio.run` path), tiered storage, Stream-based consolidation with at-least-once replay, and SSE resume that shares one offset/replay model with the Stream side

### Demo

**Act 1 — cross-session memory.** Wipe the entire hot tier ("forget everything recent") and the agent still picks up the earlier discussion — the cold tier answers and the recalled memory goes warm again:

```bash
# wipe the hot tier (simulate cache loss / TTL expiry)
docker compose exec redis redis-cli FLUSHDB

# continue the same session -> cold-tier fallback recall
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "继续上次的研究——缓冲设计定了吗？"}'
```

**Act 2 — streaming research with reconnect.** Submit a research question, events stream in real time; if the connection drops, reconnect with the last frame id — the missed frames replay first, then the live tail continues:

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking / answer / tool_start / tool_end / done

# reconnect with the last frame id
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# id: 6, 7, 8 ... (buffered gap replays) -> live tail continues
```

<!-- IMAGE SLOT: demo screenshot / asciinema GIF (insert here) -->

A fully walkable script (both acts + kill-the-consumer replay via `redis-cli`): [docs/demo.md](docs/demo.md)

### Installation

**Prerequisites**

- Python **3.12+**
- An LLM API key (`DEEPSEEK_API_KEY` by default; any OpenAI-compatible provider works)
- Docker (only for the full-stack path; the local path needs nothing else)

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env                 # fill in DEEPSEEK_API_KEY=sk-xxx
```

### Quick Start

**Service mode — first stream in 30 seconds:**

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000

# in another terminal:
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "研究：SSE 断线重连的主流方案"}'
```

Expected output (SSE frames):

```text
event: thinking   data: {"type": "thinking", "content": "…"}    <- reasoning deltas
event: answer     data: {"type": "answer",   "content": "…"}    <- answer tokens
event: tool_start data: {"type": "tool_start", "tool_name": "…"} <- tool calls
event: done       data: {"type": "done"}                         <- always terminates with done
```

Open **http://localhost:8000/docs** for the Swagger playground; after a research run, fetch history and the report:

```bash
curl -s localhost:8000/sessions/$SID/runs       # run history
curl -s localhost:8000/runs/<run_id>/report     # final report (markdown)
```

**Local mode:** just run `engram` for the full-screen TUI; type a question, `/` for command completion.

### Docker Support

```bash
cp .env.example .env     # fill in DEEPSEEK_API_KEY
docker compose up -d     # gateway + Postgres + Redis + consolidation worker
```

| Service | Role | Port |
|---|---|---|
| `gateway` | FastAPI + SSE gateway (sessions / chat / research / history + Swagger) | **8000** |
| `postgres` | Session-state checkpointer + memory cold tier + run history | 5432 |
| `redis` | Memory hot tier + consolidation Stream | 6379 |
| `consolidation-worker` | Standalone consolidation consumer (same group as the gateway's inline consumer) | — |
| `agent` | Local TUI (`tui` profile, on demand) | — |

- Wiring is automatic: the gateway receives `ENGRAM_CHECKPOINT_DSN` / `ENGRAM_REDIS_URL` / `ENGRAM_MEMORY_PG_DSN` from the compose environment
- Volumes: `.engram/pgdata` (Postgres), `.engram/redisdata` (Redis), `.engram/` (runtime journal/artifacts), `skills/`
- TUI: `docker compose run --rm agent` (first run triggers the setup wizard)
- Docker sandbox isolation: uncomment the `docker.sock` mount in `docker-compose.yml` and set `ENGRAM_SANDBOX_USE` as documented there

Full configuration, commands and troubleshooting: [Usage Guide](USAGE.md)

---

## 日本語

### これは何か

Engram は**ディープリサーチエージェント**です。ReAct カーネル、ミドルウェア優先アーキテクチャ、5 層の長期記憶、サンドボックス分離、スキル自己進化——それを**長期稼働サービスとしてパッケージ化**しました：

- **FastAPI ゲートウェイ**：セッション管理、SSE ストリーミング（チャット / リサーチ）、実行履歴、Swagger
- **階層型長期記憶**：Redis ホット層（user/thread ごとの分割キー、TTL 淘汰、読み取り時 TTL 更新）が Postgres コールド層（全量堆積）の上に乗る——ホット層を空にしても忘却しない
- **セッション状態の永続化**：LangGraph チェックポインタを Postgres に保存。サービス再起動後もセッションが継続し、複数ワーカーが同じセッション状態を共有
- **記憶統合キュー**：Redis Stream コンシューマーグループ、at-least-once（オフセット再開 + PEL リプレイ）、独立ワーカープロセスで水平スケール

同じバイナリはローカル対話モード（フルスクリーン TUI / CLI）も提供します。カーネルとサービスは同じコードを共有します。

**2764 個のテスト**がカーネルとサービスを守ります。復旧 / リプレイ / フォールバック系のスイートは CI で実物の Redis + Postgres サービスコンテナに対して実行されます。

### 何のためのものか

- **長期リサーチサービス**：質問を投げると、推論・ツール呼び出し・最終レポートを SSE でストリーミング。切断してもフレームを失わずに再接続できる
- **セッションをまたぐ記憶**：エージェントは過去のセッションを覚えている。Redis ホット層を丸ごと消しても（`FLUSHDB`）、Postgres コールド層が回答する——淘汰された記憶は呼び出し時に再び温まる
- **エージェント周辺工学のリファレンス実装**：非同期専用のゲートウェイ（`asyncio.run` の同期入口は絶対に通らない）、階層ストレージ、Stream コンシューマーグループによる at-least-once リプレイ、Stream 側と同じオフセット / リプレイモデルを共有する SSE レジューム

### デモ

**第一幕——セッションをまたぐ記憶。** ホット層を丸ごと消去（「直近の記憶をすべて忘れる」）しても、エージェントは以前の議論を継続できます——コールド層が応答し、呼び出した記憶はホット層へ再充填されます：

```bash
# ホット層を消去（キャッシュ喪失 / TTL 期限切れをシミュレート）
docker compose exec redis redis-cli FLUSHDB

# 同じセッションで会話を続ける → コールド層フォールバック
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "继续上次的研究——缓冲设计定了吗？"}'
```

**第二幕——ストリーミングリサーチと再接続。** リサーチ質問を投げるとイベントがリアルタイムで流れます。接続が切れたら最後のフレーム id を付けて再接続——欠けたフレームが先にリプレイされ、その後ライブストリームが続きます：

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking / answer / tool_start / tool_end / done

# 最後のフレーム id を付けて再接続
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# id: 6, 7, 8 ...（バッファされた欠落分がリプレイ）→ ライブストリームへ
```

<!-- IMAGE SLOT: demo screenshot / asciinema GIF (insert here) -->

実際にたどれるデモスクリプト（2 幕 + `redis-cli` でコンシューマーを落としてリプレイ確認）：[docs/demo.md](docs/demo.md)

### インストール

**前提条件**

- Python **3.12+**
- LLM API キー（デフォルトは `DEEPSEEK_API_KEY`、OpenAI 互換プロバイダーも可）
- Docker（フルスタック構成のみ。ローカル構成は他に何も不要）

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows（Linux/macOS: source .venv/bin/activate）
pip install -e ".[dev]"
cp .env.example .env                 # DEEPSEEK_API_KEY=sk-xxx を記入
```

### クイックスタート

**サービスモード——30 秒で最初のストリーム：**

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000

# 別ターミナルで:
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "研究：SSE 断线重连的主流方案"}'
```

期待される出力（SSE フレーム）：

```text
event: thinking   data: {"type": "thinking", "content": "…"}    <- 推論デルタ
event: answer     data: {"type": "answer",   "content": "…"}    <- 回答トークン
event: tool_start data: {"type": "tool_start", "tool_name": "…"} <- ツール呼び出し
event: done       data: {"type": "done"}                         <- 常に done で終了
```

ブラウザで **http://localhost:8000/docs**（Swagger）を開けばその場で API を試せます。リサーチ実行後は履歴とレポートを取得：

```bash
curl -s localhost:8000/sessions/$SID/runs       # 実行履歴
curl -s localhost:8000/runs/<run_id>/report     # 最終レポート（markdown）
```

**ローカルモード：** `engram` を実行するとフルスクリーン TUI が起動。質問を入力、`/` でコマンド補完。

### Docker サポート

```bash
cp .env.example .env     # DEEPSEEK_API_KEY を記入
docker compose up -d     # ゲートウェイ + Postgres + Redis + 統合ワーカー
```

| サービス | 役割 | ポート |
|---|---|---|
| `gateway` | FastAPI + SSE ゲートウェイ（セッション / チャット / リサーチ / 履歴 + Swagger） | **8000** |
| `postgres` | セッション状態チェックポインタ + 記憶コールド層 + 実行履歴 | 5432 |
| `redis` | 記憶ホット層 + 統合 Stream | 6379 |
| `consolidation-worker` | 独立統合コンシューマー（ゲートウェイ内蔵コンシューマーと同一グループ） | — |
| `agent` | ローカル TUI（`tui` プロファイル、オンデマンド） | — |

- 配線は自動：ゲートウェイは compose 環境から `ENGRAM_CHECKPOINT_DSN` / `ENGRAM_REDIS_URL` / `ENGRAM_MEMORY_PG_DSN` を受け取る
- データボリューム：`.engram/pgdata`（Postgres）、`.engram/redisdata`（Redis）、`.engram/`（実行時 journal / artifacts）、`skills/`
- TUI：`docker compose run --rm agent`（初回はセットアップウィザードが起動）
- Docker サンドボックス分離：`docker-compose.yml` のコメントに従い `docker.sock` マウントを解除し `ENGRAM_SANDBOX_USE` を設定

詳細な設定・コマンド・トラブルシューティング：[Usage Guide](USAGE.md)

---

## Tech Stack

<div align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.x-00BFFF?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-SSE-009488?style=flat-square)
![Redis](https://img.shields.io/badge/Redis-Streams-DC382D?style=flat-square&logo=redis&logoColor=white)
![Postgres](https://img.shields.io/badge/Postgres-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Textual](https://img.shields.io/badge/Textual-0.40+-7c6ff0?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Sandbox-2496ED?style=flat-square&logo=docker&logoColor=white)

</div>

---

## License

[MIT](LICENSE) © Engram Authors

---

<div align="center">

<sub>Built for those who care about how agents are built.</sub>

</div>
