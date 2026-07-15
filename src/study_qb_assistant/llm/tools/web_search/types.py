"""网页搜索模块的共享数据类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from study_qb_assistant.questions.models import QuestionQuery


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    """单条网页搜索证据。"""

    title: str
    url: str
    snippet: str
    source: str


class WebSearchProvider(Protocol):
    """网页搜索提供者统一接口。"""

    provider_name: str

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """检索与题目相关的网页证据。"""
