<div align="center">

<!-- IMAGE SLOT: hero banner（新しいメインビジュアルをここに挿入 — 例：docs/assets/hero.png） -->

# Engram

**あなたを覚えているリサーチアシスタント —— ネットワークが切れても進捗を失わない。**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-高速キャッシュ-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-永続メモリ-4169E1?style=for-the-badge)](https://www.postgresql.org/)

[简体中文](README.zh-CN.md) · [English](README.md) · **日本語**

アニメーションロゴ：[logo/standalone.html](logo/standalone.html) —— 文字が記憶の細胞になり、数秒ごとに光が走る：記憶が呼び起こされる瞬間。

</div>

---

## これは何か

Engram は、自分のマシン上で小さな Web サービスとして動かせる AI リサーチアシスタントです。セッションを作って質問すると、答えがリアルタイムに流れ出てきます——どう考え、何を検索し、何を書いたのかが目に見えます。読み込み中のアイコンを眺める必要はありません。大きなテーマなら研究タスクとして取り組み、完成したレポートを手渡してくれます。あとからいつでも読み返せます。

普通のチャットウィンドウと違うのは二点です：

- **覚えている。** 翌日でも、サービスを丸ごと再起動しても、前に何をしていたか覚えています。高速キャッシュを空にしても、永続ストアから静かに詳細を探し出して、何事もなかったように会話を続けます。
- **進捗を失わない。** 回答の途中で接続が切れても、再接続すれば抜けていた部分を先にまとめて届け、そのままリアルタイム出力を続けます。

ターミナル派の方へ：同じエンジンがフルスクリーンのターミナルアプリとしても動きます：`engram`。

<sub><b>仕組みをひとことで。</b> アシスタント本体は LangGraph で作られた ReAct エージェントで、それを FastAPI の Web サービスが包んでいます。記憶は二か所：古いものがある程度で自然に消える「高速キャッシュ」（Redis）と、何も失わない「永続ストア」（Postgres）。読み取りはまずキャッシュを見て、なければ永続ストアから探し、静かにキャッシュへ戻します。長い会話はバックグラウンドジョブが記憶に蒸留します——そのジョブ自体もクラッシュや再起動に耐えます。プロジェクト全体に 2,764 個の自動テストがあります。</sub>

## 何のためのものか

- **尋ねて、眺める** —— リアルタイムのストリーミングチャット：推論、ツール呼び出し、回答がその場で現れます
- **オンデマンドの深いリサーチ** —— 一つの質問がストリーミングされるレポートになり、保存されていつでも見返せます
- **文脈を持ち続ける相棒** —— セッション、記憶、レポートは再起動を越えて残ります
- **読めるサンプル** —— 自分でもエージェントサービスを作るなら、ストリーミング・永続状態・二層メモリがどう噛み合うかを、隠れた魔法なしで示す小さくテストされたコードベースです
- **ターミナルネイティブの選択肢** —— シェルで暮らす人向けの TUI / CLI

## デモ

**覚えている。** 高速キャッシュを丸ごと空にしても、会話は続きます：

```bash
# 「直近の記憶を全部忘れた」状況を再現
docker compose exec redis redis-cli FLUSHDB

# そのまま話しかける——永続ストアから詳細を探し出します
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "前回の研究、どこまで進んだっけ？"}'

event: answer
data: {"type": "answer", "content": "前回は Last-Event-ID 方式に決まりました。バッファはセッションごとのリング…"}
# ↑ この回答は永続ストアから。答えたあと自動でキャッシュに戻されます
```

**ストリーミング —— 切断しても大丈夫。** 研究の質問を投げ、接続が途中で切れたら、最後に受け取ったイベント番号を持って再接続。抜けた部分が先に届きます：

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking / answer / tool_start / tool_end / done

# 5 番目のイベントで切れた？ 最後のイベント id を付けて再接続：
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# 抜けていた 6、7… が先に届き、その後ライブ出力が続きます
```

<!-- IMAGE SLOT: デモのスクリーンショットまたは短い asciinema クリップ（ここに挿入） -->

手順を追って試したい方は、ウォークスルー：[docs/demo.md](docs/demo.md)

## インストール

必要なもの：

- Python **3.12+**
- LLM の API キー —— デフォルトは `DEEPSEEK_API_KEY`、OpenAI 互換プロバイダーなら何でも可
- Docker —— 「コマンド一発でフルスタック」のときだけ必要

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows。Linux/macOS は：source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # DEEPSEEK_API_KEY=sk-... を記入
```

## クイックスタート

サービスを起動：

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000
```

別のターミナルで、セッションを作って話しかけます：

```bash
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "SSE の切断再接続は、一般的にどう処理されていますか？"}'
```

イベントが一つずつ届きます：

```text
event: thinking   …   <- 考えている
event: answer     …   <- 回答テキスト、トークンごとに
event: tool_start …   <- 検索やツール呼び出し
event: done           <- 完了
```

ブラウザで **http://localhost:8000/docs** を開けば、すべてのエンドポイントをその場で試せます。リサーチ実行後は：

```bash
curl -s localhost:8000/sessions/$SID/runs       # 実行履歴
curl -s localhost:8000/runs/<run_id>/report     # 書き上がったレポート
```

ターミナルだけでいい？ `engram` を実行してください。

## Docker サポート

```bash
cp .env.example .env      # API キーを記入
docker compose up -d
```

| 起動するもの | ひとことで言うと | どこ |
|---|---|---|
| **gateway** | Web API —— セッション、リアルタイムチャット、リサーチ、レポート、API プレイグラウンド | http://localhost:8000 |
| **postgres** | 永続メモリ、セッション状態、実行履歴 | localhost:5432 |
| **redis** | 高速キャッシュ + バックグラウンドジョブのキュー | localhost:6379 |
| **consolidation-worker** | 古い会話を裏で記憶に整理するワーカー | — |
| **agent** | ターミナルアプリ（オンデマンド） | — |

- 配線はすべて済み——あなたが渡すのは API キーだけ。
- データは `.engram/`（ジャーナル、アーティファクト、DB・キャッシュのボリューム）と `skills/` にあります。
- Docker 内でターミナルアプリを使う：`docker compose run --rm agent`
- ツール呼び出しを Docker コンテナで隔離したい場合は、`docker-compose.yml` のコメントに従って `docker.sock` マウントを解除し、`ENGRAM_SANDBOX_USE` を設定してください。

詳しくは：[使用ガイド](resource/USAGE.ja.md) · [ウォークスルー](docs/demo.md) · [設計ノート](docs/interview-notes.md)

---

## ライセンス

[MIT](LICENSE) © Engram Authors

---

<div align="center">

<sub>エージェントがどう作られているかに関心のある人のために。</sub>

</div>
