"""网页搜索增强模块的单元测试。

本模块主要测试网页搜索数据源及大模型检索增强（RAG）功能，包括：
1. 搜索查询生成器是否能正确剔除 OCS 题型前缀（如“单选题(1分)”）；
2. 大模型检索增强提供者（SearchAugmentedModelProvider）是否成功调用包含证据的回答方法；
3. 根据环境变量动态选择/配置/禁用网页搜索提供者；
4. 复合搜索提供者（CompositeWebSearchProvider）在搜索引擎故障时的冷却熔断机制。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.models import ModelAnswer, QuestionQuery  # noqa: E402
from study_qb_assistant.providers.search_augmented import SearchAugmentedModelProvider  # noqa: E402
from study_qb_assistant.providers.web_search import (  # noqa: E402
    CompositeWebSearchProvider,
    WebSearchResult,
    build_search_provider_from_env,
    build_search_query,
)


class FakeSearchProvider:
    """单元测试专用的模拟搜索提供者。"""
    provider_name = "fake-search"

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """模拟搜索引擎的搜索行为，直接返回包含证据的可信搜索片段。

        Args:
            query: 搜索题目。
            top_k: 返回的最大条数。

        Returns:
            tuple[WebSearchResult, ...]: 模拟证据搜索结果。
        """
        return (
            WebSearchResult(
                title="标准表述",
                url="https://example.test/evidence",
                snippet="总体国家安全观以经济安全为基础。",
                source=self.provider_name,
            ),
        )


class FailingSearchProvider:
    """专门用于模拟网络超时或异常故障的搜索引擎提供者。"""
    provider_name = "failing-search"

    def __init__(self) -> None:
        """初始化并将调用计数清零。"""
        self.calls = 0

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """模拟抛出 RuntimeError 异常。

        Args:
            query: 搜索题目。
            top_k: 返回最大条数。

        Raises:
            RuntimeError: 网络超时错误。
        """
        self.calls += 1
        raise RuntimeError("network timeout")


class FakeEvidenceModel:
    """模拟支持 RAG（检索增强生成）回答模式的大模型提供者。"""
    provider_name = "fake-model"

    def __init__(self) -> None:
        """初始化证据接收计数。"""
        self.evidence_seen = 0

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """不支持外部证据输入时的普通回答，用于对比测试。

        Args:
            query: 题目。

        Returns:
            ModelAnswer: 默认的低置信度回答。
        """
        return ModelAnswer("B", "政治安全", None, 0.4)

    def answer_with_evidence(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...],
    ) -> ModelAnswer:
        """支持引入检索证据（Evidence）时的回答。

        Args:
            query: 题目。
            evidence: 传入的检索结果元组。

        Returns:
            ModelAnswer: 根据证据修正后的高置信度回答。
        """
        self.evidence_seen = len(evidence)
        return ModelAnswer("C", "经济安全", "依据证据[1]。", 0.95)


class WebSearchTests(unittest.TestCase):
    """测试网页搜索及其关联的大模型增强组件的测试类。"""

    def test_search_query_strips_ocs_prefix(self) -> None:
        """测试搜索查询转换器是否能剥离题型前缀以避免干扰搜索。
        
        例如，应将 “单选题(1分)国家安全...” 里的 “单选题(1分)” 剥除。
        """
        query = QuestionQuery(
            title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
            options=("人民安全", "政治安全", "经济安全", "军事安全"),
            question_type="single",
        )

        text = build_search_query(query)

        # 确保搜索查询文本被清洗干净
        self.assertNotIn("单选题", text)
        self.assertIn("总体国家安全观", text)

    def test_search_augmented_provider_uses_evidence_method(self) -> None:
        """测试 RAG 编排提供者是否能正确调用模型的 `answer_with_evidence` 方法。
        
        如果传入了搜索组件，应执行增强回答逻辑而不是普通逻辑。
        """
        model = FakeEvidenceModel()
        provider = SearchAugmentedModelProvider(model, FakeSearchProvider())

        answer = provider.answer(QuestionQuery(title="题目", question_type="single"))

        # 验证大模型成功感知并接收了 1 条证据
        self.assertEqual(model.evidence_seen, 1)
        # 验证返回的结果是经证据强化后的纠正选项（C）
        self.assertEqual(answer.candidate_answer, "C")

    def test_keyless_search_provider_is_default(self) -> None:
        """测试在未配置搜索密钥的环境下，默认创建的兜底搜索引擎是否非空。"""
        with patch.dict(os.environ, {}, clear=True):
            provider = build_search_provider_from_env()

        self.assertIsNotNone(provider)
        self.assertEqual(provider.provider_name, "web-search")

    def test_search_provider_can_be_disabled(self) -> None:
        """测试通过将环境变量 `STQB_WEB_SEARCH_PROVIDER` 设置为 none，可显式关闭搜索。"""
        with patch.dict(os.environ, {"STQB_WEB_SEARCH_PROVIDER": "none"}, clear=True):
            self.assertIsNone(build_search_provider_from_env())

    def test_composite_search_cools_down_failing_provider(self) -> None:
        """测试当某个搜索数据源崩溃时，Composite 复合搜索引擎的冷却（避让）机制。
        
        当发生异常时，不应该持续请求导致程序卡顿，而应当把该提供者临时冷却熔断，
        在冷却期内不再对其发起请求，直到冷却期结束后重试。
        """
        failing = FailingSearchProvider()
        # 设置故障提供者以及 60 秒的冷却重试周期
        provider = CompositeWebSearchProvider((failing,), cooldown_seconds=60)
        query = QuestionQuery(title="搜索失败冷却测试", question_type="single")

        # 第一次查询：发生异常被捕获，将 failing 放入冷却列表中，返回空
        first = provider.search(query)
        # 第二次查询：由于仍处于冷却周期，直接绕过该提供者，不触发网络请求
        second = provider.search(query)

        self.assertEqual(first, ())
        self.assertEqual(second, ())
        # 验证 failing.calls 计数为 1，代表只触发了一次真实请求，没有因并发或后续请求而发生持续的网络雪崩
        self.assertEqual(failing.calls, 1)


if __name__ == "__main__":
    unittest.main()
