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

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m engram.backend.app.gateway --port 8000
```

> On Windows the gateway entry forces `WindowsSelectorEventLoopPolicy`, which async
> Postgres drivers require — plain `uvicorn engram.backend.app.gateway.main:app`
> would start with a Proactor loop and fail once a PG DSN is configured.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn engram.backend.app.gateway.main:app --port 8000
```

**Docker (everything in one command)**

```bash
cp .env.example .env    # set DEEPSEEK_API_KEY
docker compose up -d
```

Open http://localhost:8000/docs to try the API in your browser, or start a session from the terminal:

```bash
curl -X POST localhost:8000/sessions
curl -N -X POST localhost:8000/sessions/<session_id>/chat -H "Content-Type: application/json" -d '{"message": "hello"}'
```

Prefer the terminal app? Run `engram`.

## Known limitations

- The built-in `web_search` (DuckDuckGo) needs outbound network access to
  DuckDuckGo; on restricted networks it returns no results. Research flows and
  the demo script do not depend on it — they use the local sandbox and seeded
  memories (see `docs/e2e-baseline.md`).
- Docker-backed sandboxing is optional; without `agent-sandbox` installed the
  gateway uses `LocalSandboxProvider`.

## License

[MIT](LICENSE)
