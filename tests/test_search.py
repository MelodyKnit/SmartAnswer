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
from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.exporting import write_jsonl  # noqa: E402
from study_qb_assistant.models import CanonicalQuestionRecord, QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class LocalQuestionIndexTests(unittest.TestCase):
    """测试本地题库内存检索索引的测试类。"""

    def test_exact_query_returns_source_backed_answer(self) -> None:
        """测试在输入题目完全匹配本地索引条目时，是否能正确返回由数据源支持的答案和元数据。"""
        source_path = (
            PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        )
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
        source_path = (
            PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        )
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
        """测试 LLM 自动沉淀 JSONL 能作为统一题库源参与后续本地检索。"""
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

    def test_index_can_start_empty_when_all_jsonl_paths_are_missing(self) -> None:
        """部署场景中缺少题库文件时，索引应以空库启动而不是抛异常。"""
        with tempfile.TemporaryDirectory() as directory:
            missing_verified = Path(directory) / "verified.jsonl"
            missing_ai = Path(directory) / "ai-learned.jsonl"
            index = LocalQuestionIndex.from_jsonl_files((missing_verified, missing_ai))

        status = index.status()
        result = index.query(QuestionQuery(title="尚未导入的题目", question_type="single"))

        self.assertEqual(status["record_count"], 0)
        self.assertEqual(status["source_path"], "")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_ai_learned_records_do_not_fuzzy_match_similar_questions(self) -> None:
        """LLM 自动沉淀题不能通过相似题干复用，避免选项顺序不同导致错答。"""
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
        """LLM 自动沉淀题即使题干相同，也必须选项一致才可直接复用。"""
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
        source_path = (
            PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        )
        records = tuple(iter_cmmlu_records(source_path))
        index = LocalQuestionIndex(records, source_path="sample.jsonl")

        status = index.status()

        # 校验状态信息的各项元数据
        self.assertEqual(status["record_count"], len(records))
        self.assertEqual(status["source_path"], "sample.jsonl")
        self.assertIn("CMMLU", status["source_names"])
        # 确保敏感字样如 api_key 绝对不被写到状态字典中
        self.assertNotIn("api_key", status)

    def test_answer_service_can_disable_known_rules(self) -> None:
        """当显式禁用已知规则时，不应再走固定规则答案。"""
        query = QuestionQuery(
            title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
            options=("人民安全", "政治安全", "经济安全", "军事安全"),
            question_type="single",
        )
        index = LocalQuestionIndex(())
        service = AnswerService(
            index,
            allow_model_fallback=False,
            allow_known_rules=False,
        )

        result = service.query(query)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_exact_match_prefers_reviewed_record_over_conflicting_base_record(self) -> None:
        """若同题存在冲突答案，应优先采用用户已批改确认过的题库记录。"""
        base_record = CanonicalQuestionRecord(
            question_id="base:1",
            title_raw="单选题(1分)冲突题目",
            question_type="single",
            options_raw=("A. 甲", "B. 乙"),
            answer_raw="A",
            explanation=None,
            subject="base",
            chapter=None,
            tags=("base",),
            source_name="BaseBank",
            source_url="",
            source_license="demo",
            source_split="verified",
            source_record_path="base.jsonl",
        )
        reviewed_record = CanonicalQuestionRecord(
            question_id="reviewed:1",
            title_raw="单选题(1分)冲突题目",
            question_type="single",
            options_raw=("A. 甲", "B. 乙"),
            answer_raw="B",
            explanation=None,
            subject="reviewed",
            chapter=None,
            tags=("chaoxing_reviewed",),
            source_name="ChaoxingReviewed",
            source_url="",
            source_license="user-local-reviewed",
            source_split="reviewed",
            source_record_path="reviewed.html",
        )
        index = LocalQuestionIndex((base_record, reviewed_record))

        result = index.query(
            QuestionQuery(
                title="单选题(1分)冲突题目",
                options=("A. 甲", "B. 乙"),
                question_type="single",
            ),
            allow_fuzzy=False,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(result.sources[0]["source_name"], "ChaoxingReviewed")

    def test_match_key_ignores_question_prefix_score_and_blank_noise(self) -> None:
        """题型、分值和填空占位格式变化不应导致重复题失配。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="completion:1",
                    title="1992年，邓小平发表【1】____，对整个社会主义现代化建设事业产生了重大影响。",
                    question_type="completion",
                    answer="南方谈话",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="填空题(1分) 1992年，邓小平发表【1】___，对整个社会主义现代化建设事业产生了重大影响。",
                question_type="completion",
            ),
            allow_fuzzy=False,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "南方谈话")
        self.assertEqual(result.resolution_mode, "exact_match")
        self.assertIn(result.debug["match_stage"], {"exact_key", "title_key"})

    def test_match_key_ignores_punctuation_and_full_width_noise(self) -> None:
        """标点和全半角差异只属于格式噪声，应走高可信本地命中。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="single:format",
                    title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
                    question_type="single",
                    options=("A. 人民安全", "B. 政治安全", "C. 经济安全", "D. 军事安全"),
                    answer="C",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="国家安全工作应当坚持总体国家安全观，以（）为基础",
                options=("人民安全", "政治安全", "经济安全", "军事安全"),
                question_type="single",
            ),
            allow_fuzzy=False,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "C")
        self.assertEqual(result.resolution_mode, "exact_match")

    def test_similar_completion_with_meaningful_character_difference_is_not_reused(self) -> None:
        """无选项题规范键不同且存在实义字差异时，不应靠高相似度复用答案。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="completion:semantic-a",
                    title="社会主义本质是解放生产力，发展生产力，消灭剥削。",
                    question_type="completion",
                    answer="共同富裕",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="社会主义本质是解放生产力，发展生产力，保留剥削。",
                question_type="completion",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_choice_fuzzy_requires_ordered_options_to_avoid_label_shift(self) -> None:
        """选项集合相同但页面顺序不同会导致答案标签错位，不能直接复用。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="single:order",
                    title="单选题(1分)中国的首都是哪里？",
                    question_type="single",
                    options=("北京", "上海", "广州", "深圳"),
                    answer="A",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="中国的首都是哪里",
                options=("上海", "北京", "广州", "深圳"),
                question_type="single",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_choice_fuzzy_accepts_minor_title_noise_when_ordered_options_match(self) -> None:
        """选择题题干轻微格式变化且选项顺序一致时，可以通过 n-gram 精排命中。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="multiple:fuzzy",
                    title="多选题(1分)下列属于社会主义核心价值观的是",
                    question_type="multiple",
                    options=("富强", "民主", "文明", "封建"),
                    answer="A#B#C",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="下列哪些属于社会主义核心价值观？",
                options=("富强", "民主", "文明", "封建"),
                question_type="multiple",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "A#B#C")
        self.assertEqual(result.resolution_mode, "fuzzy_match")
        self.assertEqual(result.debug["match_stage"], "ngram_fuzzy")

    def test_close_competing_candidates_are_rejected(self) -> None:
        """候选分数过近时应返回未命中，防止相似题误答。"""
        index = LocalQuestionIndex(
            (
                _record(
                    question_id="judge:beijing",
                    title="判断题(1分)中国的首都是北京。",
                    question_type="judgement",
                    options=("对", "错"),
                    answer="A",
                ),
                _record(
                    question_id="judge:nanjing",
                    title="判断题(1分)中国的首都是南京。",
                    question_type="judgement",
                    options=("对", "错"),
                    answer="B",
                ),
            )
        )

        result = index.query(
            QuestionQuery(
                title="中国的首都是东京。",
                options=("对", "错"),
                question_type="judgement",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NOT_FOUND")

    def test_update_record_persists_and_updates_memory(self) -> None:
        """测试修改题库记录时，内存索引会更新，并且如果是JSONL文件，还会更新文件内容。"""
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "test_update.jsonl"
            record = CanonicalQuestionRecord(
                question_id="test_id_123",
                title_raw="初始标题",
                question_type="single",
                options_raw=("A", "B"),
                answer_raw="A",
                explanation="旧解析",
                subject="test",
                chapter=None,
                tags=(),
                source_name="test_source",
                source_url="",
                source_license="",
                source_split="",
                source_record_path="",
            )
            write_jsonl((record,), output_path)

            # 从文件载入索引
            index = LocalQuestionIndex.from_jsonl(output_path)

            # 进行修改
            updated = index.update_record(
                "test_id_123",
                {
                    "title_raw": "更新后的标题",
                    "answer_raw": "B",
                    "explanation": "新解析",
                },
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated.title_raw, "更新后的标题")
            self.assertEqual(updated.answer_raw, "B")
            self.assertEqual(updated.explanation, "新解析")

            # 确认内存已经更新
            q_res = index.query(QuestionQuery("更新后的标题"))
            self.assertTrue(q_res.ok)
            self.assertEqual(q_res.candidate_answer, "B")

            # 确认文件内容已经更新
            reloaded_index = LocalQuestionIndex.from_jsonl(output_path)
            self.assertEqual(len(reloaded_index.records), 1)
            self.assertEqual(reloaded_index.records[0].title_raw, "更新后的标题")
            self.assertEqual(reloaded_index.records[0].answer_raw, "B")


def _record(
    *,
    question_id: str,
    title: str,
    question_type: str,
    answer: str,
    options: tuple[str, ...] = (),
) -> CanonicalQuestionRecord:
    return CanonicalQuestionRecord(
        question_id=question_id,
        title_raw=title,
        question_type=question_type,
        options_raw=options,
        answer_raw=answer,
        explanation=None,
        subject="test",
        chapter=None,
        tags=(),
        source_name="UnitTestBank",
        source_url="",
        source_license="",
        source_split="",
        source_record_path="",
    )


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
