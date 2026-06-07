"""本地规范化检索索引模块的单元测试。

本模块主要测试 `LocalQuestionIndex` 在本地检索题库时的行为，包括：
1. 题目文本完全匹配（exact_match）及正确映射选项（如 A/B/C/D）；
2. 空标题等非标准输入时的异常校验（INVALID_REQUEST）；
3. 从导出的 JSONL 格式题库中重新构建检索索引的持久化能力；
4. 索引实例的状态报告信息（status）中不包含敏感凭据安全测试。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.ingestion import iter_cmmlu_records  # noqa: E402
from study_qb_assistant.exporting import write_jsonl  # noqa: E402
from study_qb_assistant.models import CanonicalQuestionRecord, QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class LocalQuestionIndexTests(unittest.TestCase):
    """测试本地题库内存检索索引的测试类。"""

    def test_exact_query_returns_source_backed_answer(self) -> None:
        """测试在输入题目完全匹配本地索引条目时，是否能正确返回由数据源支持的答案和元数据。"""
        source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        records = tuple(iter_cmmlu_records(source_path))
        index = LocalQuestionIndex(records)

        # 发起精准查询
        result = index.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        # 验证结果
        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(result.answer_text, "肺胸膜")
        self.assertEqual(result.resolution_mode, "exact_match")
        self.assertEqual(result.sources[0]["source_name"], "CMMLU")

    def test_empty_title_is_invalid(self) -> None:
        """测试输入空标题时，索引是否能安全拦截并返回 INVALID_REQUEST 错误码。"""
        index = LocalQuestionIndex(())

        result = index.query(QuestionQuery(title=""))

        # 验证非正常请求的错误响应状态
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "INVALID_REQUEST")

    def test_index_loads_records_from_exported_jsonl(self) -> None:
        """测试通过导出的 JSONL 规范文件，能够无损重构本地索引。
        
        验证 `from_jsonl` 反序列化导入方式的正确性。
        """
        source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        records = tuple(iter_cmmlu_records(source_path))

        # 将记录写入临时的 JSONL 文件，并基于该文件载入索引
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "questions.jsonl"
            write_jsonl(records, output_path)
            index = LocalQuestionIndex.from_jsonl(output_path)

        result = index.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        # 确保通过 JSONL 还原出的索引可以正常检索出答案
        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "B")

    def test_index_loads_ai_learned_records_as_question_bank(self) -> None:
        """测试 AI 自动沉淀 JSONL 能作为统一题库源参与后续本地检索。"""
        learned_record = CanonicalQuestionRecord(
            question_id="ai:test",
            title_raw="单选题(1分)AI学习题",
            question_type="single",
            options_raw=("正确项", "干扰项"),
            answer_raw="A",
            explanation="AI 连续确认后的解析。",
            subject="ai-generated",
            chapter=None,
            tags=("ai_generated", "auto_learned", "status:trusted", "provider:test-provider"),
            source_name="AIGenerated",
            source_url="",
            source_license="user-local-ai-generated",
            source_split="trusted",
            source_record_path="ai-learned.jsonl",
            metadata={
                "ai_status": "trusted",
                "ai_confidence": "0.98",
                "ai_answer_text": "正确项",
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            learned_path = Path(directory) / "ai-learned.jsonl"
            missing_path = Path(directory) / "not-created-yet.jsonl"
            write_jsonl((learned_record,), learned_path)
            index = LocalQuestionIndex.from_jsonl_files((missing_path, learned_path))

        result = index.query(
            QuestionQuery(
                title="单选题(1分)AI学习题",
                options=("正确项", "干扰项"),
                question_type="single",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "A")
        self.assertEqual(result.answer_text, "正确项")
        self.assertEqual(result.resolution_mode, "ai_cache")
        self.assertFalse(result.review_required)
        self.assertEqual(result.sources[0]["source_name"], "AIGenerated")
        self.assertEqual(result.sources[0]["source_type"], "ai_generated_question_bank")

    def test_ai_learned_records_do_not_fuzzy_match_similar_questions(self) -> None:
        """AI 自动沉淀题不能通过相似题干复用，避免选项顺序不同导致错答。"""
        index = LocalQuestionIndex(
            (
                _ai_learned_record(
                    title="单选题(1分)常识缓存测试：1+1等于几？",
                    options=("2", "3", "4", "5"),
                    answer="A",
                    answer_text="2",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="单选题(1分)服务联调测试：1+1等于几？",
                options=("1", "2", "3"),
                question_type="single",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_ai_learned_exact_title_requires_matching_options(self) -> None:
        """AI 自动沉淀题即使题干相同，也必须选项一致才可直接复用。"""
        index = LocalQuestionIndex(
            (
                _ai_learned_record(
                    title="单选题(1分)1+1等于几？",
                    options=("2", "3", "4"),
                    answer="A",
                    answer_text="2",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="单选题(1分)1+1等于几？",
                options=("1", "2", "3"),
                question_type="single",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_status_reports_record_count_without_secrets(self) -> None:
        """测试索引状态报告，验证能正确反馈记录条数及数据源，且确保没有泄漏任何敏感密钥。"""
        source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        records = tuple(iter_cmmlu_records(source_path))
        index = LocalQuestionIndex(records, source_path="sample.jsonl")

        status = index.status()

        # 校验状态信息的各项元数据
        self.assertEqual(status["record_count"], len(records))
        self.assertEqual(status["source_path"], "sample.jsonl")
        self.assertIn("CMMLU", status["source_names"])
        # 确保敏感字样如 api_key 绝对不被写到状态字典中
        self.assertNotIn("api_key", status)


def _ai_learned_record(
    *,
    title: str,
    options: tuple[str, ...],
    answer: str,
    answer_text: str,
) -> CanonicalQuestionRecord:
    return CanonicalQuestionRecord(
        question_id=f"ai:test:{title}",
        title_raw=title,
        question_type="single",
        options_raw=options,
        answer_raw=answer,
        explanation="AI 连续确认后的解析。",
        subject="ai-generated",
        chapter=None,
        tags=("ai_generated", "auto_learned", "status:trusted", "provider:test-provider"),
        source_name="AIGenerated",
        source_url="",
        source_license="user-local-ai-generated",
        source_split="trusted",
        source_record_path="ai-learned.jsonl",
        metadata={
            "ai_status": "trusted",
            "ai_confidence": "0.99",
            "ai_answer_text": answer_text,
        },
    )


if __name__ == "__main__":
    unittest.main()
