"""网页搜索模块的 HTTP 与结果解析辅助。"""

from __future__ import annotations

import json

from ..http_client import HttpClientError, get_json, post_json
from .web_search_types import WebSearchResult


def get_search_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    timeout_seconds: float = 2.0,
) -> dict:
    """发送 GET 搜索请求并解析 JSON。"""
    try:
        return get_json(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
            proxy_env="STQB_SEARCH_PROXY",
        )
    except (HttpClientError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"search request failed: {exc}") from exc


def post_search_json(url: str, payload: dict, *, headers: dict[str, str]) -> dict:
    """发送 POST 搜索请求并解析 JSON。"""
    try:
        return post_json(
            url,
            payload,
            headers=headers,
            timeout=12,
            proxy_env="STQB_SEARCH_PROXY",
        )
    except (HttpClientError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"search request failed: {exc}") from exc


def iter_duckduckgo_related(items: object) -> tuple[WebSearchResult, ...]:
    """递归遍历 DuckDuckGo 相关主题并转换为统一结果对象。"""
    results: list[WebSearchResult] = []
    if not isinstance(items, list):
        return ()
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("Topics")
        if isinstance(nested, list):
            results.extend(iter_duckduckgo_related(nested))
            continue
        text = str(item.get("Text") or "")
        url = str(item.get("FirstURL") or "")
        if not text or not url:
            continue
        title = text.split(" - ", 1)[0].strip() or "DuckDuckGo related topic"
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=text,
                source="duckduckgo-instant-answer",
            )
        )
    return tuple(results)
