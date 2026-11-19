"""DuckDuckGo web search（ddgs 库直调，无需 API key）。

借鉴 deer-flow 的 ddg_search 模块。

2026-11-20 起 `web_search` 工具名由 tavily_search.py 注册（Tavily 主后端 +
DDG 降级 fallback 的组合实现）；本模块保留为纯函数库：导出
DEFAULT_* 常量供 fallback 复用，同名 `@tool("web_search")` 注册已移除
（一工具名一实现，builtin/__init__.py 只挂 tavily_search 的）。
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 5
DEFAULT_REGION = "wt-wt"
DEFAULT_SAFESEARCH = "moderate"
DEFAULT_BACKEND = "duckduckgo"


def ddg_search_raw(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    """DDG 匿名查询 → 归一化结果列表（tavily_search fallback 与测试复用）。"""
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


@tool("web_search_ddg", parse_docstring=True)
def web_search_ddg_tool(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Search the web via DuckDuckGo (anonymous, no API key). Direct fallback when Tavily is unavailable.

    Args:
        query: Search keywords describing what you want to find. Be specific for better results.
        max_results: Maximum number of results to return. Default is 5.
    """
    try:
        normalized = ddg_search_raw(query, max_results)
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)
        return json.dumps({"error": f"Search failed: {e}", "query": query}, ensure_ascii=False)

    if not normalized:
        return json.dumps({"error": "No results found", "query": query}, ensure_ascii=False)
    return json.dumps({"query": query, "total_results": len(normalized), "results": normalized}, indent=2, ensure_ascii=False)
