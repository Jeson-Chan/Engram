<a name="readme-top"></a>

<!-- IMAGE SLOT: 中央ロゴ / ワードマーク —— ここに挿入、幅 約45%（例：docs/assets/logo.png） -->

<p align="center">
    <a href="LICENSE" target="_blank">
        <img src="https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge" alt="ライセンス" />
    </a>
    <a href="https://www.python.org/" target="_blank">
        <img src="https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge" alt="Python 3.12+" />
    </a>
    <a href="https://fastapi.tiangolo.com/" target="_blank">
        <img src="https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge" alt="FastAPI" />
    </a>
    <a href="https://redis.io/" target="_blank">
        <img src="https://img.shields.io/badge/Redis-hot%20cache-DC382D?style=for-the-badge" alt="Redis" />
    </a>
    <a href="https://www.postgresql.org/" target="_blank">
        <img src="https://img.shields.io/badge/Postgres-memory-4169E1?style=for-the-badge" alt="Postgres" />
    </a>
    <a href="resource/USAGE.ja.md" target="_blank">
        <img src="https://img.shields.io/badge/docs-view-7c6ff0?style=for-the-badge" alt="ドキュメント" />
    </a>
</p>

<p align="center">
  <a href="./README.md">English</a> | <a href="./README.zh-CN.md">简体中文</a> | <b>日本語</b>
</p>

# Engram - あなたを覚えているリサーチアシスタント

> 「チャットウィンドウはタブを閉じた瞬間にあなたを忘れます。欲しかったのは、何日経っても、再起動しても、回線が切れても、話の筋を覚えているリサーチパートナーです。」

**Engram** は、自分のマシン上で小さなセルフホスト型 Web サービスとして動かせる AI リサーチアシスタントです。

セッションを作って質問すると、答えがリアルタイムで流れ出てきます——どう考え、何を検索し、何を書いたのかが目に見えます。大きなテーマなら深いリサーチタスクとして取り組み、完成したレポートを手渡してくれます。いつでも読み返せます。

普通のチャットウィンドウと違うのは二点：**覚えている**こと（セッションをまたぎ、再起動を越え、高速キャッシュを空にしても失わない）、そして**進捗を失わない**こと（回線が切れても、再接続すれば抜けていた部分を先に届けてくれます）。

> [!TIP]
> コマンド一つでフルスタック起動：
> ```
> docker compose up -d
> ```

<!-- VIDEO SLOT: デモ動画 / GIF —— 準備できたらここに埋め込み（<video src>、<img src>、asciinema リンク等） -->

---

## Engram の仕組み

Engram はリサーチエージェントを小さな Web サービスで包んでいます。エージェントが考え、検索し、書く——サービスがそれをブラウザやターミナルで追えるライブストリームに変え、再起動や切断に耐えるようにします。

特筆すべきは記憶です。記憶は二層に分かれます：古いものが意図的に失効する「高速キャッシュ」（Redis）と、何も失わない「永続ストア」（Postgres）。読み取りはまずキャッシュを見て、なければ永続ストアから探し、静かにキャッシュを温め直します。キャッシュを丸ごと空にしても——必要なものを引き直して、何事もなかったように続けます。

長い会話はバックグラウンドジョブが記憶に蒸留します。そのジョブ自体が耐久性のあるキューで、クラッシュや再起動にも耐え、独立したワーカープロセスとしても動きます。

<!-- IMAGE SLOT: アーキテクチャ図（ここに挿入） -->

---

## ⭐ 機能

- **🔍 ライブストリーミングチャット：** 推論、ツール呼び出し、回答がその場で現れます。
- **🔬 ディープリサーチ：** 一つの質問がストリーミングされるリサーチレポートになり、保存されて履歴に並びます。
- **🧠 再起動に耐える記憶：** セッション、記憶、履歴は再起動を越えて残ります。空にしたホットキャッシュも永続ストアから復元されます。
- **🔌 切断に強いストリーム：** 最後のイベント id を付けて再接続すれば、抜けていたイベントが先に届き、その後ライブ出力が続きます。
- **💻 セキュアサンドボックス（オプション）：** ツール呼び出しを Docker コンテナ内で実行。エージェントが書いたファイルが本当に残ります。
- **🖥️ ターミナルネイティブ：** 同じエンジンがフルスクリーン TUI やスクロール型 CLI としても動きます。

Engram はデフォルトで DeepSeek に対応し、OpenAI 互換プロバイダーならどれでも使えます。

詳しくは[ドキュメント](resource/USAGE.ja.md)へ。

---

## 🧠 記憶とあなたのデータ

すべてはあなたの環境の中で動きます——クラウドへの往復も、第三者による会話の索引化もありません。

- **高速キャッシュ**（Redis）は忘れるための設計：呼び出されなくなったホット記憶は失効します。
- **永続ストア**（Postgres）が真実の源：冷えたからといって削除されることはありません。
- データは `.engram/` と `skills/` に——バックアップも移動も削除も自由。
- モデルプロバイダーはあなたが選ぶ；ローカルプロバイダーなら推論まで手元のマシンで。

---

## 🧭 どこからでも Engram を使う

- **Web API** —— セッション、ストリーミングチャット、リサーチ、実行履歴、レポート。
- **Swagger プレイグラウンド** —— `/docs` を開けば、すべてのエンドポイントをブラウザで試せます。
- **ターミナル** —— 対話リサーチ用のフルスクリーン TUI、またはプレーンなスクロール型 CLI。
- **Docker** —— `docker compose up -d` 一つですべて起動。

---

## ⚡ クイックスタート

三つのコマンドで、フルスタックが起動します：

```bash
git clone https://github.com/Jeson-Chan/Engram.git && cd Engram
cp .env.example .env          # DEEPSEEK_API_KEY を記入
docker compose up -d          # ゲートウェイ + Postgres + Redis + ワーカー
```

ブラウザで **http://localhost:8000/docs** を開けば、すべてのエンドポイントをその場で試せます。

| 起動するもの | ひとことで言うと | どこ |
|---|---|---|
| **gateway** | Web API —— セッション、チャット、リサーチ、レポート、API プレイグラウンド | http://localhost:8000 |
| **postgres** | 永続メモリ、セッション状態、実行履歴 | localhost:5432 |
| **redis** | 高速キャッシュ + バックグラウンドジョブのキュー | localhost:6379 |
| **consolidation-worker** | 古い会話を裏で記憶に整理するワーカー | — |

- セッションを作ってチャット：`curl -s -X POST localhost:8000/sessions` で session id を取得；
  `curl -N -X POST localhost:8000/sessions/<session-id>/chat -H "Content-Type: application/json" -d '{"message": "hello"}'` でストリーミング回答が見られます。
- Docker 内のターミナルアプリ：`docker compose run --rm agent`
- データは `.engram/` と `skills/` にあります。
- Docker を使わない場合は、下のローカルインストールへ。

## 📦 インストール

Python **3.12+** と LLM の API キー（デフォルトは `DEEPSEEK_API_KEY`、OpenAI 互換プロバイダーなら何でも可）が必要です：

```bash
git clone https://github.com/Jeson-Chan/Engram.git && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows。Linux/macOS は：source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # DEEPSEEK_API_KEY=sk-... を記入
uvicorn engram.backend.app.gateway.main:app --port 8000
```

ターミナルモード（ブラウザ不要）：`engram`。

---

## 📚 ライセンス

[MIT](LICENSE) © Engram Authors

<sub>[トップへ戻る](#readme-top)</sub>
