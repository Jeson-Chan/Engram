<div align="center">

<p><img src="docs/assets/engram-logo.gif" alt="ENGRAM" width="640" /></p>

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

### 1 · TUI

```bash
pip install -e ".[dev]"        # .env に API Key を設定済み（上記参照）
engram                          # または python -m engram.backend.app.cli.main
```

これだけ —— 何でも質問してください。コックピット内：

| キー | 操作 |
|---|---|
| `Ctrl+K` | セッション切替 / 新規セッション |
| `Ctrl+O` | Run タイムライン（履歴 + 永続イベント） |
| `Ctrl+G` | Memory パネル（hot/cold/forgotten カウント） |
| `Ctrl+U` | Inspector（モデル/モード/能力 + Context 予算） |
| `Esc` | オーバーレイを閉じる |


### 2 · Web

```bash
cd web && npm install && npm run build   # 一度だけ：フロントエンドをビルド
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
```


### 3 · Docker（コマンド一発）

```bash
cp .env.example .env    # DEEPSEEK_API_KEY を記入
docker compose up -d
```

### ワンコマンドデモ

`python scripts/demo.py`：compose + シード済みセッション（「先週の
LangGraph メモリ研究」）+ Web 有効のゲートウェイを起動し、5 分デモスクリプト
を表示。デモデータの片付けは `python scripts/demo.py --clean`。詳細は
`docs/demo.md`。

## 既知の制限

- 内蔵 `web_search`（DuckDuckGo）は DuckDuckGo へのアウトバウンド接続が必要で、制限されたネットワークでは結果が空になります。リサーチフローとデモスクリプトはこれに依存しません——ローカルサンドボックスとシード済みメモリを使います（`docs/e2e-baseline.md` 参照）。
- Docker サンドボックスは任意です。`agent-sandbox` 未インストール時は `LocalSandboxProvider` を使います。

## ライセンス

[MIT](LICENSE)
