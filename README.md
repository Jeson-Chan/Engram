<a name="readme-top"></a>

<!-- IMAGE SLOT: centered logo / wordmark — insert here, width ~45% (e.g. docs/assets/logo.png) -->

<p align="center">
    <a href="LICENSE" target="_blank">
        <img src="https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge" alt="License" />
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
    <a href="USAGE.md" target="_blank">
        <img src="https://img.shields.io/badge/docs-view-7c6ff0?style=for-the-badge" alt="Documentation" />
    </a>
</p>

<p align="center">
  <b>English</b> | <a href="./README.zh-CN.md">简体中文</a> | <a href="./README.ja.md">日本語</a>
</p>

# Engram - A research assistant that remembers you

> "A chat window forgets you the moment you close the tab. I wanted a research companion that remembers the thread — across days, across restarts, across network drops."

**Engram** is an AI research assistant you run on your own machine as a small self-hosted web service.

Create a session, ask a question, and watch the answer arrive in real time — its reasoning, the searches it runs, the text it writes. Give it something bigger and it works through it as a deep research task, then hands you a finished report you can revisit anytime.

Two things make it different from a chat window: it **remembers** you across sessions and restarts (even if its fast cache is wiped), and it **never loses the thread** when the network drops — you reconnect and it fills in what you missed.

> [!TIP]
> Get the full stack running with a single command:
> ```
> docker compose up -d
> ```

<!-- VIDEO SLOT: demo video / GIF — embed here when ready (e.g. <video src>, <img src>, or an asciinema link) -->

---

## How does Engram work

Engram wraps a research agent in a small web service. The agent thinks, searches and writes — the service turns that into a live stream your browser or terminal can follow, and makes sure the work survives restarts and lost connections.

Memory is the part worth talking about. It lives in two tiers: a **fast cache** (Redis) that lets old items expire on purpose, and a **permanent store** (Postgres) that keeps everything. Reads check the cache first, fall back to the permanent store, and quietly warm the cache again. Wipe the cache entirely — the assistant simply looks up what it needs and carries on.

Long conversations are distilled into memories by a background job. That job is a durable queue, so it survives crashes and restarts too, and can run as its own worker process.

<!-- IMAGE SLOT: architecture diagram (insert here) -->

---

## ⭐ Features

- **🔍 Live streaming chat:** reasoning, tool calls and the answer appear as they happen.
- **🔬 Deep research:** one question becomes a streamed research report, saved and listed so you can come back to it.
- **🧠 Memory that survives:** sessions, memories and history persist across restarts; a wiped hot cache is recovered from the permanent store.
- **🔌 Reconnect-safe streams:** reconnect with the last event id and the missed events replay first, then live output continues.
- **💻 Secure sandbox (optional):** run tool calls inside Docker containers, so what the agent writes actually persists.
- **🖥️ Terminal native:** the same engine also runs as a full-screen TUI or a scrolling CLI.

Engram works with DeepSeek out of the box, and with any OpenAI-compatible provider.

More detail in the [docs](USAGE.md).

---

## 🧠 Memory and your data

Everything runs in your own environment — no cloud round-trip, no third-party index of your conversations.

- The **fast cache** (Redis) is designed to forget: hot memories expire unless they keep being recalled.
- The **permanent store** (Postgres) is the source of truth: nothing is deleted just because it went cold.
- Data lives in `.engram/` and `skills/` — yours to back up, move or delete.
- You choose the model provider; a local provider keeps even inference on your machine.

---

## 🧭 Access Engram from anywhere

- **Web API** — sessions, streaming chat, research, run history and reports.
- **Swagger playground** — open `/docs` and try every endpoint from the browser.
- **Terminal** — a full-screen TUI for interactive research, or a plain scrolling CLI.
- **Docker** — one `docker compose up -d` runs everything.

---

## ⚡ Quick Start

Three commands and the whole stack is up:

```bash
git clone <repo-url> && cd Engram
cp .env.example .env          # add your DEEPSEEK_API_KEY
docker compose up -d          # gateway + Postgres + Redis + worker
```

Open **http://localhost:8000/docs** — every endpoint can be tried right there in the browser.

| Runs | What it is | Where |
|---|---|---|
| **gateway** | the web API — sessions, chat, research, reports, API playground | http://localhost:8000 |
| **postgres** | permanent memory, session state, run history | localhost:5432 |
| **redis** | the fast cache + background job queue | localhost:6379 |
| **consolidation-worker** | tidies old conversations into memories in the background | — |

- Create a session, then chat: `curl -s -X POST localhost:8000/sessions` gives you a session id;
  `curl -N -X POST localhost:8000/sessions/<session-id>/chat -H "Content-Type: application/json" -d '{"message": "hello"}'` streams the answer.
- Terminal app inside Docker: `docker compose run --rm agent`
- Your data lives in `.engram/` and `skills/`.
- No Docker? See the local install below.

## 📦 Installation

Need Python **3.12+** and an LLM API key (`DEEPSEEK_API_KEY` by default; any OpenAI-compatible provider works):

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows — or: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # add DEEPSEEK_API_KEY=sk-...
uvicorn engram.backend.app.gateway.main:app --port 8000
```

Terminal mode (no browser needed): `engram`.

---

## 📚 License

[MIT](LICENSE) © Engram Authors

<sub>[Back to top](#readme-top)</sub>
