"""网页搜索模块的共享数据类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import QuestionQuery


@dataclass(slots=True)
class WebSearchResult:
    """标准化后的网页检索结果片段。"""

    title: str
    url: str
    snippet: str
    source: str


class WebSearchProvider(Protocol):
    """搜索提供商协议。"""

    provider_name: str

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """执行实时搜索并返回标准化结果。"""
