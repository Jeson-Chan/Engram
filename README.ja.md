<div align="center">

<!-- IMAGE SLOT: hero banner -->

# Engram

あなたを覚えているリサーチアシスタント。小さな Web サービスとして動かします：質問すると答えが流れ出てきて、翌日戻ってきても、何をしていたかを覚えています——サービスを再起動しても、高速キャッシュを消しても。

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent%201.x-5aa9e5?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![Redis](https://img.shields.io/badge/Redis-hot%20cache-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-memory-4169E1?style=for-the-badge)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?style=for-the-badge)](https://www.docker.com/)

[简体中文](README.zh-CN.md) · [English](README.md) · 日本語

</div>

---

## 機能

- **リアルタイムチャット** —— 推論・検索・回答がその場で見える。読み込みアイコンを眺めなくていい
- **リサーチモード** —— ひとつの質問がストリーミングレポートになり、いつでも読み返せる
- **長期記憶** —— セッションは再起動に耐える。高速キャッシュを消しても何も失わない
- **切断しても失わない** —— 接続が切れても、止まったところから続きを再開できる
- **ターミナルでも使える** —— フルスクリーン TUI と CLI を同梱（`engram`）

## Demo

## インストール

Python 3.12+ と DeepSeek の API キーが必要です（OpenAI 互換なら他社でも可）。

```bash
git clone https://github.com/Jeson-Chan/Engram.git
cd Engram
pip install -e ".[dev]"
cp .env.example .env
```

`.env` を開いて `DEEPSEEK_API_KEY=sk-...` を記入します。

## クイックスタート

**Windows（PowerShell）**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m engram.backend.app.gateway --port 8000
```

> Windows ではゲートウェイの起動エントリが `WindowsSelectorEventLoopPolicy`
> を強制します（非同期 Postgres ドライバの要件）。素の
> `uvicorn engram.backend.app.gateway.main:app` は Proactor ループで起動し、
> PG DSN を設定すると起動に失敗します。

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn engram.backend.app.gateway.main:app --port 8000
```

**Docker（コマンド一発ですべて起動）**

```bash
cp .env.example .env    # DEEPSEEK_API_KEY を記入
docker compose up -d
```

ブラウザで http://localhost:8000/docs を開けば API をその場で試せます。ターミナルからセッションを作ることもできます：

```bash
curl -X POST localhost:8000/sessions
curl -N -X POST localhost:8000/sessions/<session_id>/chat -H "Content-Type: application/json" -d '{"message": "こんにちは"}'
```

ターミナルアプリがいい方は `engram` を実行してください。

ブラウザがいい方は Web 研究ワークベンチをビルドして有効化：

```bash
cd web && npm install && npm run build
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
# http://127.0.0.1:8000/app を開く —— セッション / ストリーミング対話・リサーチ /
# Run インスペクタ / Memory エクスプローラ / 再接続レジューム
```

ワンコマンドデモ（compose + シード済みセッション + 5 分スクリプト）：
`python scripts/demo.py`。詳細は `docs/demo.md` と `docs/api.md`。

## 既知の制限

- 内蔵 `web_search`（DuckDuckGo）は DuckDuckGo へのアウトバウンド接続が必要で、制限されたネットワークでは結果が空になります。リサーチフローとデモスクリプトはこれに依存しません——ローカルサンドボックスとシード済みメモリを使います（`docs/e2e-baseline.md` 参照）。
- Docker サンドボックスは任意です。`agent-sandbox` 未インストール時は `LocalSandboxProvider` を使います。

## ライセンス

[MIT](LICENSE)
