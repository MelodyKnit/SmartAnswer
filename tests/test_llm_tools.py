"""LLM 工具契约、注册表和适配器测试。"""

from __future__ import annotations

import unittest

from study_qb_assistant.llm.contracts import EvidenceRetrievalPort
from study_qb_assistant.llm.tools import BaseLlmTool, LlmToolRegistry, LocalRagTool, WebSearchTool
from study_qb_assistant.questions.models import QueryResult, QuestionQuery


class FakeIndex:
    def __init__(self) -> None:
        self.allow_fuzzy: bool | None = None

    def query(self, query: QuestionQuery, *, allow_fuzzy: bool = True) -> QueryResult:
        self.allow_fuzzy = allow_fuzzy
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer="A",
            answer_text="答案一",
            explanation=None,
            confidence=0.99,
            resolution_mode="exact_match",
            review_required=False,
        )

    def status(self) -> dict[str, object]:
        return {"record_count": 1}


class FakeSearchProvider:
    provider_name = "fake-search"

    def search(self, query: QuestionQuery, *, top_k: int = 5):
        from study_qb_assistant.llm.providers.web_search_types import WebSearchResult

        return (
            WebSearchResult(
                title="证据",
                url="https://example.com/evidence",
                snippet=query.title,
                source=self.provider_name,
            ),
        )


class LlmToolTests(unittest.TestCase):
    def test_abstract_tool_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            BaseLlmTool()

    def test_local_rag_delegates_without_changing_fuzzy_policy(self) -> None:
        index = FakeIndex()
        tool = LocalRagTool(index)  # type: ignore[arg-type]

        result = tool.query(QuestionQuery(title="测试题"), allow_fuzzy=False)

        self.assertTrue(result.ok)
        self.assertFalse(index.allow_fuzzy)

    def test_registry_rejects_duplicate_names_and_filters_capabilities(self) -> None:
        registry = LlmToolRegistry((LocalRagTool(FakeIndex()),))  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "名称重复"):
            registry.register(LocalRagTool(FakeIndex()))  # type: ignore[arg-type]
        self.assertEqual(len(registry.by_capability("answer_retrieval")), 1)

    def test_web_search_tool_satisfies_evidence_protocol(self) -> None:
        tool = WebSearchTool(FakeSearchProvider())  # type: ignore[arg-type]

        result = tool.retrieve(QuestionQuery(title="测试题"))

        self.assertIsInstance(tool, EvidenceRetrievalPort)
        self.assertTrue(result.ok)
        self.assertEqual(result.evidence[0].source, "fake-search")


if __name__ == "__main__":
    unittest.main()
