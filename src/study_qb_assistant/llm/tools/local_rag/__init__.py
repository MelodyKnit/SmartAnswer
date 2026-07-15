"""本地题库 RAG 工具适配器。"""

from __future__ import annotations

from study_qb_assistant.questions.models import QueryResult, QuestionQuery
from ....search import LocalQuestionIndex
from ..base import AnswerRetrievalTool


class LocalRagTool(AnswerRetrievalTool):
    """把 LocalQuestionIndex 暴露为 LLM 答案检索工具。"""

    tool_name = "local-rag"

    def __init__(self, index: LocalQuestionIndex) -> None:
        self.index = index

    def query(self, query: QuestionQuery, *, allow_fuzzy: bool = True) -> QueryResult:
        return self.index.query(query, allow_fuzzy=allow_fuzzy)

    def status(self) -> dict[str, object]:
        return {**super().status(), "index": self.index.status()}
