<a name="readme-top"></a>

<!-- IMAGE SLOT: centered logo / wordmark — insert here, width ~45% (e.g. docs/assets/logo.png) -->

<p align="center">
    <a href="USAGE.md" target="_blank">
        <img src="https://img.shields.io/badge/docs-view-blue?logo=readthedocs&logoColor=white" alt="Documentation" />
    </a>
    <a href="docs/demo.md" target="_blank">
        <img src="https://img.shields.io/badge/demo-walkthrough-blue" alt="Demo" />
    </a>
    <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" />
    <img src="https://img.shields.io/badge/FastAPI-web%20service-blue?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Redis-hot%20cache-blue?logo=redis&logoColor=white" alt="Redis" />
    <img src="https://img.shields.io/badge/Postgres-memory-blue?logo=postgresql&logoColor=white" alt="Postgres" />
    <a href="LICENSE" target="_blank">
        <img src="https://img.shields.io/static/v1?label=license&message=MIT&color=blue" alt="License" />
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

<!-- IMAGE SLOT: main screenshot — chat streaming an answer (insert here) -->

---

## How does Engram work

Engram wraps a research agent in a small web service. The agent thinks, searches and writes — the service turns that into a live stream your browser or terminal can follow, and makes sure the work survives restarts and lost connections.

Memory is the part worth talking about. It lives in two tiers: a **fast cache** (Redis) that lets old items expire on purpose, and a **permanent store** (Postgres) that keeps everything. Reads check the cache first, fall back to the permanent store, and quietly warm the cache again. Wipe the cache entirely — the assistant simply looks up what it needs and carries on.

Long conversations are distilled into memories by a background job. That job is a durable queue, so it survives crashes and restarts too, and can run as its own worker process.

<!-- IMAGE SLOT: architecture diagram (insert here) -->

---

## ⭐ Features

- **🔍 Live streaming chat:** reasoning, tool calls and the answer appear as they happen — no spinner, no waiting for the whole reply.
- **🔬 Deep research:** one question becomes a streamed research report, saved and listed so you can come back to it later.
- **🧠 Memory that survives:** sessions, memories and history persist across service restarts; a wiped hot cache is recovered from the permanent store and re-warmed on demand.
- **🔌 Reconnect-safe streams:** if the connection drops, reconnect with the last event id and the missed events replay first, then live output continues.
- **💻 Secure sandbox (optional):** run tool calls inside Docker containers with path enforcement, so what the agent writes actually persists.
- **🖥️ Terminal native:** the same engine also runs as a full-screen TUI or a scrolling CLI.
- **🧩 Readable, tested core:** a small, well-factored codebase with injectable seams — 2,764 automated tests; the recovery and replay suites run against real Redis and Postgres in CI.

Engram works with DeepSeek out of the box, and with any OpenAI-compatible provider.

More detail in the [docs](USAGE.md).

---

## 🧠 Memory and your data

Everything runs in your own environment — no cloud round-trip, no third-party index of your conversations.

- The **fast cache** (Redis) is designed to forget: hot memories expire unless they keep being recalled.
- The **permanent store** (Postgres) is the source of truth: nothing is deleted just because it went cold.
- Data lives in `.engram/` (journals, artifacts, database and cache volumes) and `skills/` — yours to back up, move or delete.
- You choose the model provider; a local provider keeps even inference on your machine.

---

## 🧭 Access Engram from anywhere

- **Web API** — a FastAPI service with sessions, streaming chat, research, run history and reports.
- **Swagger playground** — open `/docs` and try every endpoint from the browser.
- **Terminal** — a full-screen TUI for interactive research, or a plain scrolling CLI.
- **CLI one-shot** — `engram run "question"` prints the report and exits.
- **Docker** — one `docker compose up -d` runs the gateway, the databases and the background worker.

---

## 🎬 Demo

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

**It streams — and survives a dropped connection.**

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

---

## 📦 Installation

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

## ⚡ Quick Start

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

## 🐳 Docker Support

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

---

## 📚 License

[MIT](LICENSE) © Engram Authors

<sub>[Back to top](#readme-top)</sub>
