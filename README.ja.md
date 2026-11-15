<a name="readme-top"></a>

<!-- IMAGE SLOT: 中央ロゴ / ワードマーク —— ここに挿入、幅 約45%（例：docs/assets/logo.png） -->

<p align="center">
    <a href="resource/USAGE.ja.md" target="_blank">
        <img src="https://img.shields.io/badge/docs-view-blue?logo=readthedocs&logoColor=white" alt="ドキュメント" />
    </a>
    <a href="docs/demo.md" target="_blank">
        <img src="https://img.shields.io/badge/demo-walkthrough-blue" alt="デモ" />
    </a>
    <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" />
    <img src="https://img.shields.io/badge/FastAPI-web%20service-blue?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Redis-hot%20cache-blue?logo=redis&logoColor=white" alt="Redis" />
    <img src="https://img.shields.io/badge/Postgres-memory-blue?logo=postgresql&logoColor=white" alt="Postgres" />
    <a href="LICENSE" target="_blank">
        <img src="https://img.shields.io/static/v1?label=license&message=MIT&color=blue" alt="ライセンス" />
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

<!-- IMAGE SLOT: メインスクリーンショット —— 回答をストリーミング中のチャット（ここに挿入） -->

---

## Engram の仕組み

Engram はリサーチエージェントを小さな Web サービスで包んでいます。エージェントが考え、検索し、書く——サービスがそれをブラウザやターミナルで追えるライブストリームに変え、再起動や切断に耐えるようにします。

特筆すべきは記憶です。記憶は二層に分かれます：古いものが意図的に失効する「高速キャッシュ」（Redis）と、何も失わない「永続ストア」（Postgres）。読み取りはまずキャッシュを見て、なければ永続ストアから探し、静かにキャッシュを温め直します。キャッシュを丸ごと空にしても——必要なものを引き直して、何事もなかったように続けます。

長い会話はバックグラウンドジョブが記憶に蒸留します。そのジョブ自体が耐久性のあるキューで、クラッシュや再起動にも耐え、独立したワーカープロセスとしても動きます。

<!-- IMAGE SLOT: アーキテクチャ図（ここに挿入） -->

---

## ⭐ 機能

- **🔍 ライブストリーミングチャット：** 推論、ツール呼び出し、回答がその場で現れます——スピナーで待つ必要も、全文生成を待つ必要もありません。
- **🔬 ディープリサーチ：** 一つの質問がストリーミングされるリサーチレポートになり、保存されて履歴に並び、いつでも見返せます。
- **🧠 再起動に耐える記憶：** セッション、記憶、履歴は再起動を越えて残ります。空にしたホットキャッシュも永続ストアから復元され、呼び出し時に温め直されます。
- **🔌 切断に強いストリーム：** 接続が切れたら、最後のイベント id を付けて再接続——抜けていたイベントが先に届き、その後ライブ出力が続きます。
- **💻 セキュアサンドボックス（オプション）：** ツール呼び出しを Docker コンテナ内でパス制約付きに実行。エージェントが書いたファイルが本当に残ります。
- **🖥️ ターミナルネイティブ：** 同じエンジンがフルスクリーン TUI やスクロール型 CLI としても動きます。
- **🧩 読めて、テストされた核：** 小さく分割され、差し替え可能な継ぎ目を持つコードベース——2,764 個の自動テスト。復旧・リプレイ系のスイートは CI で実物の Redis と Postgres に対して実行。

Engram はデフォルトで DeepSeek に対応し、OpenAI 互換プロバイダーならどれでも使えます。

詳しくは[ドキュメント](resource/USAGE.ja.md)へ。

---

## 🧠 記憶とあなたのデータ

すべてはあなたの環境の中で動きます——クラウドへの往復も、第三者による会話の索引化もありません。

- **高速キャッシュ**（Redis）は忘れるための設計：呼び出されなくなったホット記憶は失効します。
- **永続ストア**（Postgres）が真実の源：冷えたからといって削除されることはありません。
- データは `.engram/`（ジャーナル、アーティファクト、DB・キャッシュのボリューム）と `skills/` に——バックアップも移動も削除も自由。
- モデルプロバイダーはあなたが選ぶ；ローカルプロバイダーなら推論まで手元のマシンで。

---

## 🧭 どこからでも Engram を使う

- **Web API** —— FastAPI サービス：セッション、ストリーミングチャット、リサーチ、実行履歴、レポート。
- **Swagger プレイグラウンド** —— `/docs` を開けば、すべてのエンドポイントをブラウザで試せます。
- **ターミナル** —— 対話リサーチ用のフルスクリーン TUI、またはプレーンなスクロール型 CLI。
- **CLI ワンショット** —— `engram run "質問"` でレポートを出力して終了。
- **Docker** —— `docker compose up -d` 一つでゲートウェイ、データベース、バックグラウンドワーカーが起動。

---

## 🎬 デモ

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

**ストリーミング —— 切断しても大丈夫。**

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

---

## 📦 インストール

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

## ⚡ クイックスタート

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

## 🐳 Docker サポート

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

---

## 📚 ライセンス

[MIT](LICENSE) © Engram Authors

<sub>[トップへ戻る](#readme-top)</sub>
