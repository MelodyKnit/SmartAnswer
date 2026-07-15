"""联网搜索证据工具适配器。"""

from __future__ import annotations

import time

from study_qb_assistant.questions.models import QuestionQuery
from ...contracts.tools import EvidenceItem, ToolExecutionResult
from .providers import build_search_provider, build_search_provider_from_env
from .types import WebSearchProvider, WebSearchResult
from ..base import EvidenceRetrievalTool


class WebSearchTool(EvidenceRetrievalTool):
    """把现有网页搜索提供者适配为证据检索工具。"""

    tool_name = "web-search"

    def __init__(self, provider: WebSearchProvider) -> None:
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    def retrieve(self, query: QuestionQuery, *, top_k: int = 5) -> ToolExecutionResult:
        started = time.perf_counter()
        try:
            results = self.provider.search(query, top_k=top_k)
        except Exception as exc:
            return ToolExecutionResult(
                ok=False,
                tool_name=self.tool_name,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                error=str(exc),
            )
        evidence = tuple(
            EvidenceItem(
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                source=item.source,
            )
            for item in results
        )
        return ToolExecutionResult(
            ok=True,
            tool_name=self.tool_name,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            evidence=evidence,
        )

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """保留旧搜索提供者接口，便于一版兼容迁移。"""

        result = self.retrieve(query, top_k=top_k)
        if not result.ok:
            raise RuntimeError(result.error or "web search failed")
        return tuple(
            WebSearchResult(
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                source=item.source,
            )
            for item in result.evidence
        )


__all__ = [
    "WebSearchProvider",
    "WebSearchResult",
    "WebSearchTool",
    "build_search_provider",
    "build_search_provider_from_env",
]
