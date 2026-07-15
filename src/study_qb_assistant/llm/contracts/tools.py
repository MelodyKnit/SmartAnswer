"""LLM 工具端口与共享结果结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from study_qb_assistant.questions.models import QueryResult, QuestionQuery


@dataclass(slots=True, frozen=True)
class EvidenceItem:
    """可交给模型使用的单条证据。"""

    title: str
    url: str
    snippet: str
    source: str


@dataclass(slots=True, frozen=True)
class ToolExecutionResult:
    """统一描述工具执行结果、耗时和错误。"""

    ok: bool
    tool_name: str
    elapsed_ms: float
    evidence: tuple[EvidenceItem, ...] = ()
    answer: QueryResult | None = None
    error: str | None = None


@runtime_checkable
class AnswerRetrievalPort(Protocol):
    """直接返回题库答案的检索工具端口。"""

    tool_name: str

    def query(self, query: QuestionQuery, *, allow_fuzzy: bool = True) -> QueryResult:
        """检索题目答案。"""


@runtime_checkable
class EvidenceRetrievalPort(Protocol):
    """返回模型证据的检索工具端口。"""

    tool_name: str

    def retrieve(self, query: QuestionQuery, *, top_k: int = 5) -> ToolExecutionResult:
        """检索与题目相关的证据。"""
