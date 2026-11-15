<div align="center">

<!-- IMAGE SLOT: hero banner (insert new art here — e.g. docs/assets/hero.png) -->

# Engram

**A research assistant that remembers you — even when the network drops.**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-fast%20cache-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-memory-4169E1?style=for-the-badge)](https://www.postgresql.org/)

[简体中文](README.zh-CN.md) · **English** · [日本語](README.ja.md)

Animated wordmark: [logo/standalone.html](logo/standalone.html) — letters as memory cells, a glint sweeping across: a memory being recalled.

</div>

---

## What is this

Engram is an AI research assistant you run on your own machine as a small web service. Create a session, ask a question, and the answer streams in as it happens — you watch it think, search, and write instead of staring at a spinner. Give it something bigger and it works through it as a research task, then hands you a finished report you can come back to.

Two things make it different from a chat window:

- **It remembers.** Come back tomorrow — or restart the whole service — and it still knows what you were working on. Wipe its fast cache, and it quietly looks the details up in its permanent store and carries on as if nothing happened.
- **It doesn't lose the thread.** If your connection drops mid-answer, reconnect and it first hands you whatever you missed, then keeps streaming from where it left off.

Prefer the terminal? The same engine runs as a full-screen terminal app: `engram`.

<sub><b>Under the hood, in one paragraph.</b> The assistant is a ReAct agent built with LangGraph and wrapped in a FastAPI web service. Memories live in two tiers: a fast cache (Redis) that lets old items expire on purpose, and a permanent store (Postgres) that keeps everything. Reads try the cache first, fall back to the permanent store, and quietly re-warm the cache. Long conversations trigger a background job that distills them into memories — and that job survives crashes too. The whole project ships with 2,764 automated tests.</sub>

## What is this for

- **Ask and watch** — live streaming chat: reasoning, tool calls and the answer appear as they happen
- **Deep research on demand** — one request becomes a streamed report, saved so you can revisit it
- **A companion that keeps context** — sessions, memories and reports survive restarts
- **A readable example** — if you are building agent services yourself, this is a small, well-tested codebase where streaming, durable state and two-tier memory fit together without hidden magic
- **A terminal-native option** — full TUI and CLI for people who live in the shell

## Demo

**It remembers.** Wipe the entire fast cache to prove the point — the conversation still continues:

```bash
# simulate "we forgot everything recent"
docker compose exec redis redis-cli FLUSHDB

# keep talking; it looks the details up in the permanent store
curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "Where were we on the buffer design?"}'

event: answer
data: {"type": "answer", "content": "Last time you settled on Last-Event-ID; the buffer is a per-session ring…"}
# ^ answered from the permanent store, then re-cached automatically
```

**It streams — and survives a dropped connection.** Submit a research question; if the connection drops, reconnect and the missed part arrives first:

```bash
curl -N -X POST localhost:8000/sessions/$SID/research \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# event: thinking  /  answer  /  tool_start  /  tool_end  /  done

# dropped at event 5? reconnect carrying the last event id:
curl -N -H "Last-Event-ID: 5" -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "..."}'
# the missed events (6, 7, …) arrive first, then live output continues
```

<!-- IMAGE SLOT: demo screenshot or short asciinema clip (insert here) -->

Prefer to click through it step by step? The walkthrough: [docs/demo.md](docs/demo.md)

## Installation

You need:

- Python **3.12+**
- An LLM API key — `DEEPSEEK_API_KEY` by default; any OpenAI-compatible provider works
- Docker — only for the one-command full-stack path

```bash
git clone <repo-url> && cd Engram
python -m venv .venv
.venv\Scripts\activate            # Windows — or: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # add DEEPSEEK_API_KEY=sk-...
```

## Quick Start

Start the service:

```bash
uvicorn engram.backend.app.gateway.main:app --port 8000
```

In another terminal, create a session and say hello:

```bash
SID=$(curl -s -X POST localhost:8000/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

curl -N -X POST localhost:8000/sessions/$SID/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "How do most systems handle dropped SSE connections?"}'
```

Events arrive one by one:

```text
event: thinking   …   <- it is reasoning
event: answer     …   <- answer text, token by token
event: tool_start …   <- it searches or calls a tool
event: done           <- finished
```

Open **http://localhost:8000/docs** to try every endpoint from your browser. After a research run:

```bash
curl -s localhost:8000/sessions/$SID/runs       # past runs
curl -s localhost:8000/runs/<run_id>/report     # the written report
```

Just want the terminal? Run `engram`.

## Docker Support

```bash
cp .env.example .env      # add your API key
docker compose up -d
```

| Starts up | In plain words | Where |
|---|---|---|
| **gateway** | the web API — sessions, live chat, research, reports, API playground | http://localhost:8000 |
| **postgres** | permanent memory, session state, run history | localhost:5432 |
| **redis** | the fast cache + the background job queue | localhost:6379 |
| **consolidation-worker** | tidies old conversations into memories in the background | — |
| **agent** | the terminal app, on demand | — |

- Everything is wired for you — you only supply the API key.
- Your data lives in `.engram/` (journals, artifacts, database and cache volumes) and `skills/`.
- Terminal app inside Docker: `docker compose run --rm agent`
- Want tool calls isolated in Docker containers? Uncomment the `docker.sock` mount in `docker-compose.yml` and set `ENGRAM_SANDBOX_USE` as explained in its comments.

More: [Usage Guide](USAGE.md) · [walkthrough](docs/demo.md) · [design notes](docs/interview-notes.md)

---

## License

[MIT](LICENSE) © Engram Authors

---

<div align="center">

<sub>Built for those who care about how agents are built.</sub>

</div>
