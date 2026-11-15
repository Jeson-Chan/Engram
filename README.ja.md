<div align="center">

<!-- IMAGE SLOT: hero banner -->

# Engram

あなたを覚えているリサーチアシスタント。小さな Web サービスとして動かします：質問すると答えが流れ出てきて、翌日戻ってきても、何をしていたかを覚えています——サービスを再起動しても、高速キャッシュを消しても。

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)

[简体中文](README.zh-CN.md) · [English](README.md) · **日本語**

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
uvicorn engram.backend.app.gateway.main:app --port 8000
```

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

ブラウザで **http://localhost:8000/docs** を開けば API をその場で試せます。ターミナルからセッションを作ることもできます：

```bash
curl -X POST localhost:8000/sessions
curl -N -X POST localhost:8000/sessions/<session_id>/chat -H "Content-Type: application/json" -d '{"message": "こんにちは"}'
```

ターミナルアプリがいい方は `engram` を実行してください。

## ライセンス

[MIT](LICENSE)
