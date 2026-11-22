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
```

## Quick Start

```bash
engram init
engram doctor
engram
```

The first launch asks for an API key (or run `engram init`). That's it —
the TUI is self-contained: chat, memory, skills all run in-process, no
backend or Docker required. `engram doctor` gives an optional health
check (capability matrix + connectivity).

Inside the cockpit:

| Keys | Action |
|---|---|
| `Ctrl+K` | session switcher / new session |
| `Ctrl+O` | Run timeline (history + persisted events) |
| `Ctrl+G` | Memory panel (hot/cold/forgotten counts) |
| `Ctrl+U` | Inspector (model/mode/capabilities + runtime environment) |
| `Esc` | close any overlay |

## Web workbench

Build the frontend once, then pick how to run the backend. Both work;
they differ in memory tiers and how config changes take effect.

```bash
cd web
npm install
npm run build
cd ..
```

### Local backend (venv)

Runs in your Python environment. Memory stays Markdown (single tier)
unless you configure Redis/PG (`/guide` in the TUI can walk you through
it). Config changes to `.env` need a gateway restart.

bash / zsh:

```bash
ENGRAM_WEB_UI_ENABLED=true python -m engram.backend.app.gateway --port 8000
```

PowerShell:

```powershell
$env:ENGRAM_WEB_UI_ENABLED = "true"
python -m engram.backend.app.gateway --port 8000
```

cmd:

```cmd
set ENGRAM_WEB_UI_ENABLED=true
python -m engram.backend.app.gateway --port 8000
```

### Docker backend

```bash
docker compose up -d
```

Memory tiers (Redis hot / Postgres cold) are injected by compose — no
DSN needed in `.env`. Config changes require rebuilding the containers:

```bash
docker compose up -d --build
```

The image bakes the code, and compose overrides `.env` for tier DSNs.

The workbench is served at `http://localhost:8000/app` either way.

## Known limitations

- The built-in `web_search` (DuckDuckGo) needs outbound network access to
  DuckDuckGo; on restricted networks it returns no results. Research flows do
  not depend on it — they use the local sandbox and seeded memories.
- Docker-backed sandboxing is optional; without `agent-sandbox` installed the
  gateway uses `LocalSandboxProvider`.

## License

[MIT](LICENSE)
