"""Tavily web search tool（API 后端，主搜索；DDG 匿名降级 fallback）。

修复背景（2026-11-20 线上故障）：DuckDuckGo 匿名直连对容器出口 IP
静默限流——连续 11 次 "No results found"（含 "news" 这种极宽泛词），
属于外部服务不可用而非查询词问题。接入 Tavily（LLM agent 专用搜索
API，免费 dev 额度）做主后端，DDG 保留为无 key 环境的 fallback。

选择顺序：
1. TAVILY_API_KEY 配置 → Tavily 主后端（结构化结果）
2. 无 key / Tavily 网络失败 → DDG（ddgs 匿名，尽力而为）

返回契约与 ddg_search 对齐（tool_call_middleware._EMPTY_RE 识别
空结果格式），LLM 侧零改动。
"""

from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 5


def _tavily_key() -> str | None:
    """Tavily key（env 直读；.env 由 gateway load_dotenv 灌入）。"""
    return (os.environ.get("TAVILY_API_KEY") or "").strip() or None


def _tavily_search(query: str, max_results: int) -> list[dict] | None:
    """Tavily 查询 → 归一化结果；None = 不可用（无 key / 失败，走 fallback）。"""
    if _tavily_key() is None:
        return None
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=_tavily_key())
        response = client.search(query, max_results=max_results)
        results = response.get("results", []) or []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in results
        ]
    except Exception as e:
        logger.warning("Tavily search failed (fallback to DDG): %s", e)
        return None


def _ddg_search(query: str, max_results: int) -> list[dict]:
    """DDG 匿名查询（原 ddg_search 路径，降级保留）。"""
    from engram.backend.agents.agent_tools.builtin.ddg_search import (
        DEFAULT_BACKEND,
        DEFAULT_REGION,
        DEFAULT_SAFESEARCH,
    )
    from ddgs import DDGS

    ddgs = DDGS(timeout=30)
    results = ddgs.text(
        query,
        region=DEFAULT_REGION,
        safesearch=DEFAULT_SAFESEARCH,
        max_results=max_results,
        backend=DEFAULT_BACKEND,
    )
    results = list(results) if results else []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", r.get("link", "")),
            "content": r.get("body", r.get("snippet", "")),
        }
        for r in results
    ]


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Search the web for information. Use this tool to find current information, news, articles, and facts from the internet.

    Args:
        query: Search keywords describing what you want to find. Be specific for better results.
        max_results: Maximum number of results to return. Default is 5.
    """
    # 主后端：Tavily（key 配置时）
    results = _tavily_search(query, max_results)
    backend = "tavily"
    # 降级：DDG 匿名（无 key 或 Tavily 失败）
    if results is None:
        try:
            results = _ddg_search(query, max_results)
        except Exception as e:
            logger.error("DDG fallback search failed: %s", e)
            return json.dumps(
                {"error": f"Search failed: {e}", "query": query},
                ensure_ascii=False,
            )
        backend = "duckduckgo"

    if not results:
        return json.dumps({"error": "No results found", "query": query}, ensure_ascii=False)

    return json.dumps(
        {
            "query": query,
            "backend": backend,
            "total_results": len(results),
            "results": results,
        },
        indent=2,
        ensure_ascii=False,
    )
