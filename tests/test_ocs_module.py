"""OCS 模块契约与扩展边界测试。"""

from __future__ import annotations

import unittest

from study_qb_assistant.adapters.ocs import (
    BaseOcsQuestionTypeHandler,
    DefaultOcsIntegration,
    OcsIntegrationPort,
    OcsQuestionTypeRegistry,
)
from study_qb_assistant.adapters.ocs.config import load_ocs_client_script_source
from study_qb_assistant.adapters.ocs.question_types import SingleChoiceOcsHandler
from study_qb_assistant.questions.models import QueryResult, QuestionQuery


def successful_result(question_type: str, answer: str = "A") -> QueryResult:
    return QueryResult(
        ok=True,
        query=QuestionQuery(
            title="测试题",
            options=("答案一", "答案二"),
            question_type=question_type,
        ),
        candidate_answer=answer,
        answer_text="答案一",
        explanation="测试解析",
        confidence=0.99,
        resolution_mode="exact_match",
        review_required=False,
    )


class OcsModuleTests(unittest.TestCase):
    def test_default_integration_satisfies_port(self) -> None:
        self.assertIsInstance(DefaultOcsIntegration(), OcsIntegrationPort)

    def test_base_handler_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            BaseOcsQuestionTypeHandler()

    def test_registry_rejects_duplicate_aliases(self) -> None:
        registry = OcsQuestionTypeRegistry((SingleChoiceOcsHandler(),))
        with self.assertRaisesRegex(ValueError, "别名重复"):
            registry.register(SingleChoiceOcsHandler())

    def test_private_reader_type_is_not_mapped_to_completion(self) -> None:
        for private_type in ("reader", "line"):
            with self.subTest(private_type=private_type):
                payload = DefaultOcsIntegration().format_response(
                    successful_result(private_type)
                )

                self.assertEqual(payload["data"]["answer"], "A")
                self.assertEqual(payload["data"]["ai"]["ocs_question_type"], "unsupported")
                self.assertFalse(payload["data"]["ai"]["ocs_type_supported"])
                self.assertEqual(
                    payload["data"]["ai"]["ocs_raw_question_type"],
                    private_type,
                )

    def test_unknown_choice_type_keeps_legacy_label_normalization(self) -> None:
        payload = DefaultOcsIntegration().format_response(successful_result("unknown"))

        self.assertEqual(payload["data"]["answer"], "A")
        self.assertEqual(payload["data"]["ai"]["ocs_question_type"], "single")

    def test_unknown_judgement_type_prefers_judgement_strategy(self) -> None:
        result = successful_result("unknown")
        result.query.title = "判断题测试"
        result.answer_text = "正确"

        payload = DefaultOcsIntegration().format_response(result)

        self.assertEqual(payload["data"]["answer"], "对")
        self.assertEqual(payload["data"]["ai"]["ocs_question_type"], "judgement")

    def test_packaged_client_script_is_readable(self) -> None:
        self.assertIn("// ==UserScript==", load_ocs_client_script_source())


if __name__ == "__main__":
    unittest.main()
