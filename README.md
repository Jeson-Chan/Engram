<div align="center">

<p><img src="docs/assets/engram-logo.gif" alt="ENGRAM" width="640" /></p>

# Engram

A research assistant that remembers you. It runs as a small web service: ask a question, watch the answer stream in, come back later and it still knows what you were working on, even after a restart, or after its fast cache is wiped.

[![License: MIT](https://img.shields.io/badge/License-MIT-7c6ff0?style=for-the-badge)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-45c4b8?style=for-the-badge)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20service-009488?style=for-the-badge)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent%201.x-5aa9e5?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![Redis](https://img.shields.io/badge/Redis-hot%20cache-DC382D?style=for-the-badge)](https://redis.io/)
[![Postgres](https://img.shields.io/badge/Postgres-memory-4169E1?style=for-the-badge)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?style=for-the-badge)](https://www.docker.com/)

[简体中文](README.zh-CN.md) · English · [日本語](README.ja.md)

</div>

---

## Features

- **Live chat** — reasoning, searches and the answer appear while they happen, not after a spinner
- **Research mode** — one question becomes a streamed report you can revisit any time
- **Long-term memory** — sessions survive restarts; wiping the fast cache loses nothing
- **Reconnect without loss** — a dropped connection picks up where it stopped
- **Works in the terminal too** — full-screen TUI and CLI included (`engram`)

## Demo

## Installation

Needs Python 3.12+ and a DeepSeek API key (any OpenAI-compatible provider also works).

```bash
git clone https://github.com/Jeson-Chan/Engram.git
cd Engram
pip install -e ".[dev]"
cp .env.example .env
```

Open `.env` and set `DEEPSEEK_API_KEY=sk-...`.

## Quick Start

Two ways to run Engram — the full-screen **TUI** (keyboard-first research
cockpit) or the **Web workbench** (three-pane browser UI). Both share the same
sessions, memory, and runs.

### 1 · TUI — the research cockpit

```bash
pip install -e ".[dev]"        # after setting API keys in .env (see above)
engram                          # or: python -m engram.backend.app.cli.main
```

That's it — ask anything. Inside the cockpit:

| Keys | Action |
|---|---|
| `Ctrl+K` | session switcher / new session |
| `Ctrl+O` | Run timeline (history + persisted events) |
| `Ctrl+G` | Memory panel (hot/cold/forgotten counts) |
| `Ctrl+U` | Inspector (model/mode/capabilities + context budget) |
| `Esc` | close any overlay |

Panels read the gateway's read-only API when one is running
(`ENGRAM_GATEWAY_URL`, default `http://127.0.0.1:8000`) and show an offline
state otherwise — chat/research itself always works.

### 2 · Web — the research workbench

```bash
cd web && npm install && npm run build   # once: build the frontend
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
# open http://127.0.0.1:8000/app
```

> On Windows, always start the gateway with
> `python -m engram.backend.app.gateway` — it forces the Selector event loop
> async Postgres requires (plain `uvicorn ...:app` fails with a PG DSN).

Three panes: sessions / streaming chat & research / Run Inspector with Memory
Explorer. Refresh restores the session, history, and last run. All endpoints:
`/docs`; the full walkthrough: `docs/api.md`.

### Docker (everything in one command)

```bash
cp .env.example .env    # set DEEPSEEK_API_KEY
docker compose up -d
```

### One-command demo

`python scripts/demo.py` starts compose + a seeded session ("上周的 LangGraph
记忆研究") + the gateway with the web UI, and prints a 5-minute script. Clean
demo data with `python scripts/demo.py --clean`. Details: `docs/demo.md`.

## Known limitations

- The built-in `web_search` (DuckDuckGo) needs outbound network access to
  DuckDuckGo; on restricted networks it returns no results. Research flows and
  the demo script do not depend on it — they use the local sandbox and seeded
  memories (see `docs/e2e-baseline.md`).
- Docker-backed sandboxing is optional; without `agent-sandbox` installed the
  gateway uses `LocalSandboxProvider`.

## License

[MIT](LICENSE)
