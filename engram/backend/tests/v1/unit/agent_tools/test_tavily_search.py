"""web_search 主备切换测试 — Tavily 主后端 + DDG 匿名 fallback。

背景（2026-11-20 故障修复）：DDG 匿名直连对容器出口 IP 静默限流，
web_search 11 连空；接入 Tavily 做主后端。这里锁切换逻辑契约：
- TAVILY_API_KEY 配置 → 走 Tavily（backend 字段 = tavily）
- 无 key → DDG fallback（backend = duckduckgo）
- Tavily 异常 → 降级 DDG，不向上抛
- 空结果 → "No results found"（契约与旧 ddg_search 对齐）
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from engram.backend.agents.agent_tools.builtin import tavily_search


class _FakeTavilyClient:
    """TavilyClient 桩（monkeypatch tavily.TavilyClient）。"""

    def __init__(self, results: list[dict] | None = None, error: Exception | None = None) -> None:
        self._results = results or []
        self._error = error

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        return {"results": self._results[:max_results]}


def _run_tool(query: str = "test query") -> dict:
    out = tavily_search.web_search_tool.invoke({"query": query})
    return json.loads(out)


def test_tavily_backend_used_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """key 配置 → Tavily 主后端，结果结构化带 backend 标注。"""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    fake = _FakeTavilyClient(
        results=[
            {"title": "AI funding hits record", "url": "https://example.com/1", "content": "record 2024"},
            {"title": "VC trends", "url": "https://example.com/2", "content": "more"},
        ]
    )
    monkeypatch.setattr("tavily.TavilyClient", lambda api_key: fake)
    body = _run_tool("AI funding")
    assert body["backend"] == "tavily"
    assert body["total_results"] == 2
    assert body["results"][0]["url"] == "https://example.com/1"


def test_ddg_fallback_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 key → DDG fallback（backend = duckduckgo）。"""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(
        tavily_search, "_ddg_search",
        lambda query, max_results: [
            {"title": "ddg result", "url": "https://ddg.example", "content": "from ddg"},
        ],
    )
    body = _run_tool("anything")
    assert body["backend"] == "duckduckgo"
    assert body["total_results"] == 1


def test_ddg_fallback_when_tavily_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tavily 网络异常 → 降级 DDG，不向上抛。"""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(
        "tavily.TavilyClient",
        lambda api_key: _FakeTavilyClient(error=RuntimeError("network down")),
    )
    monkeypatch.setattr(
        tavily_search, "_ddg_search",
        lambda query, max_results: [
            {"title": "ddg fallback", "url": "https://ddg.example", "content": "still works"},
        ],
    )
    body = _run_tool("anything")
    assert body["backend"] == "duckduckgo"
    assert body["results"][0]["title"] == "ddg fallback"


def test_empty_results_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """空结果 → 'No results found'（与旧 ddg_search 契约一致，
    tool_call_middleware._EMPTY_RE 靠这个格式识别）。"""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr("tavily.TavilyClient", lambda api_key: _FakeTavilyClient(results=[]))
    body = _run_tool("obscure query")
    assert body == {"error": "No results found", "query": "obscure query"}


def test_tool_name_unchanged() -> None:
    """工具名仍为 web_search（注册与 LLM 工具调用零改动）。"""
    assert tavily_search.web_search_tool.name == "web_search"
