"""答题编排服务与模型兜底逻辑的单元测试。

本模块主要对 `AnswerService` 的核心能力进行测试，包括：
1. 本地题库完全匹配逻辑（exact_match）；
2. 模型兜底匹配逻辑（llm_fallback）；
3. 已知公式的快速判定（known_rule）；
4. 基于多次高置信度模型回答的 AI 结果自动晋升与缓存机制（ai_cache）；
5. 冲突或非安全答案的缓存过滤。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.llm.cache import LlmAnswerCache  # noqa: E402
from study_qb_assistant.ingestion import iter_cmmlu_records  # noqa: E402
from study_qb_assistant.models import ModelAnswer, QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.storage.question_repository import SqlAlchemyQuestionRepository  # noqa: E402
import study_qb_assistant.answer_quality as answer_quality_module  # noqa: E402

_TEST_RULES_PAYLOAD = {
    "option_rules": [
        {"needles": ["国家安全工作", "以()为基础"], "answers": ["经济安全"]},
        {"needles": ["从现在到2020年", "决胜期"], "answers": ["建成小康社会"]},
    ]
}


class FakeModelProvider:
    """用于单元测试的模拟模型提供者类。

    该类记录被调用的次数，并每次返回一个固定的 ModelAnswer。
    """

    provider_name = "fake-provider"

    def __init__(self) -> None:
        """初始化 FakeModelProvider，将调用次数清零。"""
        self.calls = 0

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """根据输入的查询题目，返回一个固定的模拟答案。

        Args:
            query: 查询的题目对象。

        Returns:
            ModelAnswer: 包含模拟答案和置信度的模型回答对象。
        """
        self.calls += 1
        return ModelAnswer(
            candidate_answer="A",
            answer_text="模拟答案",
            explanation=f"模型解释: {query.title}",
            confidence=0.42,
        )


class SequenceModelProvider:
    """序列型模型提供者，按预设的答案顺序依次返回。

    用于模拟模型在多次请求下返回不同答案的场景。
    """

    provider_name = "sequence-provider"

    def __init__(self, answers: tuple[ModelAnswer, ...]) -> None:
        """初始化序列模型提供者。

        Args:
            answers: 预设的答案序列，调用时会按顺序逐个返回。
        """
        self.answers = list(answers)
        self.calls = 0

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """依次返回预设的下一个答案。如果答案已被耗尽，则返回默认备用答案。

        Args:
            query: 查询的题目对象。

        Returns:
            ModelAnswer: 预设的或默认的答案对象。
        """
        self.calls += 1
        if self.answers:
            return self.answers.pop(0)
        return ModelAnswer("A", "复用答案", "重复确认。", 0.99)


class AnswerServiceTests(unittest.TestCase):
    """测试 AnswerService 答题编排服务的测试类。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = tempfile.TemporaryDirectory()
        cls._rules_path = Path(cls._tempdir.name) / "answer-quality-rules.json"
        cls._rules_path.write_text(
            json.dumps(_TEST_RULES_PAYLOAD, ensure_ascii=False), encoding="utf-8"
        )
        cls._previous_rules_path = os.environ.get("STQB_ANSWER_RULES_PATH")
        os.environ["STQB_ANSWER_RULES_PATH"] = str(cls._rules_path)
        _clear_rule_caches()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._previous_rules_path is None:
            os.environ.pop("STQB_ANSWER_RULES_PATH", None)
        else:
            os.environ["STQB_ANSWER_RULES_PATH"] = cls._previous_rules_path
        _clear_rule_caches()
        cls._tempdir.cleanup()

    def test_local_hit_does_not_call_model_by_default(self) -> None:
        """测试当本地题库完全匹配时，默认情况下不会调用大模型。

        验证在这种场景下，匹配模式是否正确记录为 exact_match，且模型提供者的调用次数为 0。
        """
        service, provider = _service_with_cmmlu(allow_model_fallback=True)

        # "壁胸膜的分部不包括" 是 CMMLU 原始测试集解剖学分类下的真题
        result = service.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(provider.calls, 0)  # 应当从本地索引命中，不调用模型
        self.assertEqual(result.resolution_mode, "exact_match")

    def test_model_fallback_is_labeled_for_review(self) -> None:
        """测试在本地题库未命中的情况下，回退到大模型解析时是否正确标记为“待审核”。

        验证在此模式下返回的 resolution_mode 是否为 llm_fallback，且 review_required 为 True。
        """
        service, provider = _service_with_cmmlu(allow_model_fallback=True)

        # 输入一道本地必定不存在的题目
        result = service.query(
            QuestionQuery(title="一道本地题库里不存在的题目", question_type="single")
        )

        self.assertTrue(result.ok)
        self.assertEqual(provider.calls, 1)  # 调用了一次模型
        self.assertEqual(result.resolution_mode, "llm_fallback")
        self.assertTrue(result.review_required)  # 回退到大模型的回答默认需要人工审核
        self.assertEqual(result.sources[0]["source_type"], "model_provider")

    def test_no_local_bank_mode_skips_local_index_and_uses_model_fallback(self) -> None:
        """测试无本地题库模式会跳过本地命中，直接走模型兜底链路。"""
        service, provider = _service_with_cmmlu(allow_model_fallback=True)
        service.no_local_bank_mode = True
        service.allow_known_rules = False

        result = service.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        self.assertTrue(result.ok)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.resolution_mode, "llm_fallback")
        self.assertEqual(result.candidate_answer, "A")

    def test_known_rule_runs_before_model_fallback(self) -> None:
        """测试已知公式修复规则是否会在大模型兜底前先一步被拦截匹配。

        即使本地没有这道题，只要题目满足已知公式，也应当直接由公式库匹配出答案，不触发大模型调用。
        """
        service, provider = _service_with_cmmlu(allow_model_fallback=True)

        # 这道题符合国家安全基础的已知公式
        result = service.query(
            QuestionQuery(
                title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
                options=("人民安全", "政治安全", "经济安全", "军事安全"),
                question_type="single",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(provider.calls, 0)  # 没有调用大模型
        self.assertEqual(result.candidate_answer, "C")
        self.assertEqual(result.answer_text, "经济安全")
        self.assertEqual(result.resolution_mode, "known_rule")
        self.assertFalse(result.review_required)  # 已知题库公式判定为高可信度，不需要人工审核

    def test_known_rule_works_without_model_provider(self) -> None:
        """测试在未配置任何大模型提供者时，已知公式修复逻辑是否依然能正常运作。"""
        source_path = (
            PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
        )
        # 实例化一个没有 model_provider 的服务
        service = AnswerService(LocalQuestionIndex(tuple(iter_cmmlu_records(source_path))))

        # 传入带有已知匹配模式的十九大决胜期题目
        result = service.query(
            QuestionQuery(
                title="单选题(1分)党的十九大指出，从现在到2020年，是全面( )决胜期。",
                options=("深化改革", "建成小康社会", "从严治党", "依法治国"),
                question_type="single",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(result.resolution_mode, "known_rule")

    def test_model_explanation_can_enrich_local_result(self) -> None:
        """测试在启用 explain_local_matches 选项时，即使本地命中了答案，是否也会调用大模型来丰富解释。"""
        # 显式开启 explain_local_matches = True
        service, provider = _service_with_cmmlu(explain_local_matches=True)

        result = service.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        self.assertTrue(result.ok)
        self.assertEqual(provider.calls, 1)  # 即使本地命中，也调用了模型获取解释
        self.assertEqual(result.candidate_answer, "B")
        self.assertIn("模型解释", result.explanation or "")

    def test_ai_cache_promotes_after_repeated_high_confidence_answer(self) -> None:
        """测试多次重复的高置信度模型回答是否会将该条目晋升并存入 LLM 缓存中。

        设置最小确认次数为 2。验证：
        - 第一次查询：状态为 pending（待确认），请求大模型；
        - 第二次查询：状态晋升为 trusted（可信），请求大模型并写入缓存；
        - 第三次查询：状态为 ai_cache（读取缓存），不再请求大模型且无需审核。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider(
                (
                    ModelAnswer("A", "复用答案", "第一次高置信。", 0.99),
                    ModelAnswer("A", "复用答案", "第二次高置信。", 0.98),
                )
            )
            # 配置确认次数限制 min_confirmations = 2
            learned_path = Path(temp_dir) / "ai-learned.jsonl"
            service = _service_with_cache(provider, learned_path)
            query = QuestionQuery(
                title="单选题(1分)缓存测试题",
                options=("复用答案", "干扰项"),
                question_type="single",
            )

            first = service.query(query)
            second = service.query(query)
            third = service.query(query)
            persisted_records = _read_jsonl(learned_path)

        # 第一次查询：尚未达到确认次数，需调用大模型
        self.assertEqual(first.resolution_mode, "llm_fallback")
        self.assertEqual(first.debug["llm_cache_status"], "pending")

        # 第二次查询：达到确认次数限制，触发晋升至 trusted，并写入本地缓存文件
        self.assertEqual(second.resolution_mode, "llm_fallback")
        self.assertEqual(second.debug["llm_cache_status"], "trusted")

        # 第三次查询：直接读取 LLM 缓存，不调用模型
        self.assertEqual(third.resolution_mode, "ai_cache")
        self.assertEqual(provider.calls, 2)  # 模型总共被调用了 2 次
        self.assertFalse(third.review_required)  # 缓存的答案不再需要人工审核
        self.assertEqual(len(persisted_records), 1)
        learned = persisted_records[0]
        self.assertEqual(learned["source_name"], "AIGenerated")
        self.assertEqual(learned["answer_raw"], "A")
        self.assertIn("ai_generated", learned["tags"])
        self.assertIn("auto_learned", learned["tags"])
        self.assertIn("status:trusted", learned["tags"])
        self.assertEqual(learned["metadata"]["ai_status"], "trusted")
        self.assertEqual(learned["metadata"]["ai_answer_text"], "复用答案")

    def test_trusted_ai_cache_direct_hit_uses_ai_question_bank_source(self) -> None:
        """测试受信任 AI 条目直接命中时也使用统一 AI 题库来源标记。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider((ModelAnswer("A", "复用答案", "高置信。", 0.99),))
            cache = LlmAnswerCache(
                Path(temp_dir) / "ai-learned.jsonl", min_confidence=0.95, min_confirmations=1
            )
            query = QuestionQuery(
                title="单选题(1分)直接命中AI题库",
                options=("复用答案", "干扰项"),
                question_type="single",
            )
            cache.record_model_answer(
                query, provider.answer(query), provider_name=provider.provider_name
            )
            service = AnswerService(
                LocalQuestionIndex(()),
                model_provider=provider,
                allow_model_fallback=True,
                llm_answer_cache=cache,
            )

            result = service.query(query)

        self.assertEqual(result.resolution_mode, "ai_cache")
        self.assertEqual(result.sources[0]["source_name"], "AIGenerated")
        self.assertEqual(result.sources[0]["source_type"], "ai_generated_question_bank")
        self.assertEqual(result.sources[0]["source_license"], "user-local-ai-generated")
        self.assertTrue(str(result.sources[0]["source_id"]).startswith("ai:"))

    def test_ai_cache_does_not_promote_conflicting_answers(self) -> None:
        """测试如果模型在连续查询中返回了冲突的答案（例如 A 之后返回 B），则不应晋升缓存。

        验证即使后续再次返回 A，缓存状态仍应标为 conflict。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider(
                (
                    ModelAnswer("A", "第一个答案", "第一次。", 0.99),
                    ModelAnswer("B", "第二个答案", "冲突。", 0.99),
                    ModelAnswer("A", "第一个答案", "再次。", 0.99),
                )
            )
            service = _service_with_cache(provider, Path(temp_dir) / "ai-learned.jsonl")
            query = QuestionQuery(
                title="单选题(1分)缓存冲突测试题",
                options=("第一个答案", "第二个答案"),
                question_type="single",
            )

            first = service.query(query)
            second = service.query(query)
            third = service.query(query)

        # 第一次：待确认
        self.assertEqual(first.debug["llm_cache_status"], "pending")
        # 第二次：大模型给出了不同的答案 B，触发冲突标记 conflict
        self.assertEqual(second.debug["llm_cache_status"], "conflict")
        # 第三次：即使模型重回正确答案 A，由于之前已经记录过冲突，状态信号仍为 conflict
        self.assertEqual(third.debug["llm_cache_status"], "conflict")
        self.assertEqual(third.resolution_mode, "llm_fallback")
        self.assertEqual(provider.calls, 3)

    def test_ai_cache_treats_reordered_multiple_labels_as_same_answer(self) -> None:
        """测试多选题标签顺序不同不会导致 AI 学习题库冲突。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider(
                (
                    ModelAnswer("C#A#B", "甲；乙；丙", "第一次。", 0.99),
                    ModelAnswer("B#C#A", "乙；丙；甲", "第二次。", 0.99),
                )
            )
            service = _service_with_cache(provider, Path(temp_dir) / "ai-learned.jsonl")
            query = QuestionQuery(
                title="多选题(1分)缓存顺序测试题",
                options=("甲", "乙", "丙", "丁"),
                question_type="multiple",
            )

            first = service.query(query)
            second = service.query(query)
            third = service.query(query)

        self.assertEqual(first.debug["llm_cache_status"], "pending")
        self.assertEqual(second.debug["llm_cache_status"], "trusted")
        self.assertEqual(third.resolution_mode, "ai_cache")
        self.assertEqual(third.candidate_answer, "A#B#C")
        self.assertEqual(provider.calls, 2)

    def test_ai_cache_skips_internally_inconsistent_answer(self) -> None:
        """测试如果大模型生成的答案内部字段冲突（如 A 与文本不对应），则该答案不应被存入缓存。

        验证这种答案将被标记为 unsafe_not_cached，在下次有一致的答案返回时重新变为 pending。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider(
                (
                    # candidate_answer="A" 对应选项“第一个答案”，但 answer_text 填了“第二个答案”，构成不一致
                    ModelAnswer("A", "第二个答案", "候选和文本冲突。", 0.99),
                    ModelAnswer("A", "第一个答案", "一致。", 0.99),
                )
            )
            service = _service_with_cache(provider, Path(temp_dir) / "ai-learned.jsonl")
            query = QuestionQuery(
                title="单选题(1分)缓存安全测试题",
                options=("第一个答案", "第二个答案"),
                question_type="single",
            )

            first = service.query(query)
            second = service.query(query)

        # 第一次：解析出的答案在 is_cache_safe_answer 中判定为 False，不加入缓存，标记为 unsafe_not_cached
        self.assertEqual(first.debug["llm_cache_status"], "unsafe_not_cached")
        # 第二次：模型给出了合规安全的答案，重新转入 pending 状态进行多轮确认
        self.assertEqual(second.debug["llm_cache_status"], "pending")
        self.assertEqual(provider.calls, 2)

    def test_low_confidence_ai_answer_is_visible_but_not_indexed(self) -> None:
        """低置信度 AI 答案应入库可见，但不能自动进入本地命中链路。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider(
                (
                    ModelAnswer("A", "公私合营", "低置信度解析。", 0.43),
                    ModelAnswer("A", "公私合营", "再次低置信度解析。", 0.44),
                )
            )
            repository = SqlAlchemyQuestionRepository(Path(temp_dir) / "questions.sqlite3")
            service = AnswerService(
                LocalQuestionIndex(()),
                model_provider=provider,
                allow_model_fallback=True,
                trusted_confidence_threshold=0.95,
            )
            service.question_repository = repository
            query = QuestionQuery(
                title="填空题(1分)国家资本主义的高级形式是【1】____。",
                options=("公私合营", "农业互助组"),
                question_type="single",
            )

            first = service.query(query)
            stored = repository.list_question_records(keyword="公私合营")
            second = service.query(query)

        self.assertTrue(first.ok)
        self.assertEqual(first.debug["question_bank_status"], "low_confidence")
        self.assertEqual(stored[0].metadata["status"], "low_confidence")
        self.assertEqual(second.resolution_mode, "llm_fallback")
        self.assertEqual(provider.calls, 2)

    def test_high_confidence_ai_answer_is_persisted_and_indexed(self) -> None:
        """高置信度 AI 答案应入库并进入本地命中链路，重复题不再调用模型。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider((ModelAnswer("A", "公私合营", "可信解析。", 0.99),))
            repository = SqlAlchemyQuestionRepository(Path(temp_dir) / "questions.sqlite3")
            service = AnswerService(
                LocalQuestionIndex(()),
                model_provider=provider,
                allow_model_fallback=True,
                trusted_confidence_threshold=0.95,
            )
            service.question_repository = repository
            query = QuestionQuery(
                title="单选题(1分)国家资本主义的高级形式是【1】____。",
                options=("公私合营", "农业互助组"),
                question_type="single",
            )

            first = service.query(query)
            stored = repository.list_question_records(status="trusted", keyword="可信解析")
            second = service.query(query)

        self.assertEqual(first.debug["question_bank_status"], "trusted")
        self.assertEqual(stored[0].metadata["status"], "trusted")
        self.assertNotEqual(second.resolution_mode, "llm_fallback")
        self.assertEqual(provider.calls, 1)

    def test_no_local_bank_mode_still_persists_ai_answer(self) -> None:
        """无本地题库模式只跳过读取本地题库，不应阻止 AI 答题记录落库。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = SequenceModelProvider((ModelAnswer("A", "公私合营", "模式测试。", 0.99),))
            repository = SqlAlchemyQuestionRepository(Path(temp_dir) / "questions.sqlite3")
            service = AnswerService(
                LocalQuestionIndex(()),
                model_provider=provider,
                allow_model_fallback=True,
                no_local_bank_mode=True,
            )
            service.question_repository = repository
            query = QuestionQuery(
                title="单选题(1分)无本地题库模式仍需沉淀。",
                options=("公私合营", "农业互助组"),
                question_type="single",
            )

            result = service.query(query)
            stored = repository.list_question_records(keyword="模式测试")

        self.assertTrue(result.ok)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].metadata["status"], "trusted")


def _service_with_cmmlu(
    *,
    allow_model_fallback: bool = False,
    explain_local_matches: bool = False,
) -> tuple[AnswerService, FakeModelProvider]:
    """快捷构建包含局部 CMMLU 题库索引以及 FakeModelProvider 的服务实例。

    Args:
        allow_model_fallback: 是否允许模型兜底。
        explain_local_matches: 本地命中时是否请求大模型解释。

    Returns:
        tuple[AnswerService, FakeModelProvider]: 构造的服务与模拟大模型实例。
    """
    source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
    index = LocalQuestionIndex(tuple(iter_cmmlu_records(source_path)))
    provider = FakeModelProvider()
    service = AnswerService(
        index,
        model_provider=provider,
        allow_model_fallback=allow_model_fallback,
        explain_local_matches=explain_local_matches,
    )
    return service, provider


def _service_with_cache(provider: SequenceModelProvider, cache_path: Path) -> AnswerService:
    """构建用于测试 LLM 缓存逻辑的空索引服务实例。

    Args:
        provider: 序列型大模型模拟器。
        cache_path: 缓存文件路径。

    Returns:
        AnswerService: 实例化的服务对象。
    """
    index = LocalQuestionIndex(())
    return AnswerService(
        index,
        model_provider=provider,
        allow_model_fallback=True,
        llm_answer_cache=LlmAnswerCache(cache_path, min_confidence=0.95, min_confirmations=2),
    )


def _read_jsonl(path: Path) -> list[dict]:
    """读取测试生成的 JSONL 记录。"""
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == "__main__":
    unittest.main()


def _clear_rule_caches() -> None:
    answer_quality_module._configured_option_rules.cache_clear()
    answer_quality_module._configured_completion_rules.cache_clear()
    answer_quality_module._load_rules_payload.cache_clear()
