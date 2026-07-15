"""网页搜索模块的 HTTP 与结果解析辅助。"""

from __future__ import annotations

import json
import time
from typing import Any

from study_qb_assistant.llm.http_client import HttpClientError, get_json, post_json, request_text
from .types import WebSearchResult

SEARCH_PROXY_ENV = "STQB_SEARCH_PROXY"


def get_search_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    timeout_seconds: float = 8.0,
    retries: int = 2,
    proxy_url: str | None = None,
) -> dict:
    """发送搜索 GET 请求并返回 JSON 对象。"""

    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            if proxy_url:
                import os

                os.environ[SEARCH_PROXY_ENV] = proxy_url
            payload = get_json(
                url,
                params=params,
                timeout=timeout_seconds,
                proxy_env=SEARCH_PROXY_ENV,
            )
            return payload if isinstance(payload, dict) else {}
        except (HttpClientError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    raise RuntimeError(str(last_error) if last_error else "search json request failed")


def post_search_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 12.0,
    retries: int = 2,
    proxy_url: str | None = None,
) -> dict:
    """发送搜索 POST 请求并返回 JSON 对象。"""

    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            if proxy_url:
                import os

                os.environ[SEARCH_PROXY_ENV] = proxy_url
            response = post_json(
                url,
                payload,
                headers=headers,
                timeout=timeout_seconds,
                proxy_env=SEARCH_PROXY_ENV,
            )
            return response if isinstance(response, dict) else {}
        except (HttpClientError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    raise RuntimeError(str(last_error) if last_error else "search post request failed")


def get_search_text(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 8.0,
    retries: int = 2,
    proxy_url: str | None = None,
) -> str:
    """发送搜索 GET 请求并返回 HTML 文本。"""

    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            if proxy_url:
                import os

                os.environ[SEARCH_PROXY_ENV] = proxy_url
            return request_text(
                "GET",
                url,
                params=params,
                headers=headers,
                timeout=timeout_seconds,
                proxy_env=SEARCH_PROXY_ENV,
            )
        except HttpClientError as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    raise RuntimeError(str(last_error) if last_error else "search text request failed")


def iter_duckduckgo_related(items: Any) -> tuple[WebSearchResult, ...]:
    """递归解析 DuckDuckGo RelatedTopics 为统一搜索结果。"""

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
        text = str(item.get("Text") or "").strip()
        url = str(item.get("FirstURL") or "").strip()
        if not text or not url:
            continue
        title = text.split(" - ", 1)[0].strip() or "DuckDuckGo"
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=text,
                source="duckduckgo-instant-answer",
            )
        )
    return tuple(results)
