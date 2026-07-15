"""LLM 工具抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from study_qb_assistant.questions.models import QueryResult, QuestionQuery
from ..contracts.tools import ToolExecutionResult


class BaseLlmTool(ABC):
    """项目内部 LLM 工具的公共基础类。"""

    capabilities: frozenset[str]

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """返回注册表使用的稳定工具名称。"""

    def status(self) -> dict[str, object]:
        """返回工具名称和能力清单。"""

        return {
            "tool_name": self.tool_name,
            "capabilities": sorted(self.capabilities),
            "enabled": True,
        }


class AnswerRetrievalTool(BaseLlmTool):
    """直接返回题库答案的工具基类。"""

    capabilities = frozenset({"answer_retrieval"})

    @abstractmethod
    def query(self, query: QuestionQuery, *, allow_fuzzy: bool = True) -> QueryResult:
        """检索题目答案。"""


class EvidenceRetrievalTool(BaseLlmTool):
    """返回可供模型使用证据的工具基类。"""

    capabilities = frozenset({"evidence_retrieval"})

    @abstractmethod
    def retrieve(self, query: QuestionQuery, *, top_k: int = 5) -> ToolExecutionResult:
        """检索题目证据。"""
