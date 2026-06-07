"""OCS 响应适配器行为的单元测试。

本模块主要测试如何将内部的查询/回答结果规范化转换为 OCS 协议定义的标准 JSON 响应结构。
OCS 规范详见前端接口标准设计文档。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.adapters import to_ocs_response  # noqa: E402
from study_qb_assistant.ingestion import iter_cmmlu_records  # noqa: E402
from study_qb_assistant.models import QueryResult, QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class OcsAdapterTests(unittest.TestCase):
    """测试将查询结果映射为 OCS API 格式响应的测试类。"""

    def test_success_response_contains_answer_and_metadata(self) -> None:
        """测试正常查到答案时，生成的 OCS 响应是否包含合规的答案、置信度及元数据。
        
        验证 code 为 0，且 payload 中正确携带了 candidate_answer 以及数据源 CMMLU 信息。
        """
        index = _cmmlu_index()
        # 查询 CMMLU 中的真题
        result = index.query(QuestionQuery(title="壁胸膜的分部不包括", question_type="single"))

        payload = to_ocs_response(result)

        # 校验 OCS 定义的响应数据结构
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["answer"], "B")
        self.assertEqual(payload["data"]["answer_text"], "肺胸膜")
        self.assertEqual(payload["data"]["ai"]["confidence"], 0.99)
        self.assertEqual(payload["data"]["ai"]["resolution_mode"], "exact_match")
        self.assertEqual(payload["data"]["ai"]["sources"][0]["source_name"], "CMMLU")

    def test_error_response_preserves_question_and_error_code(self) -> None:
        """测试查询异常或未查到结果时，生成的 OCS 响应是否能正确返回错误码且标记需要审核。
        
        验证无效请求（如空标题）下的 code 为 1，且 error_code 被设置为 INVALID_REQUEST。
        """
        # 输入一个非法的空标题查询
        result = LocalQuestionIndex(()).query(QuestionQuery(title="", question_type="single"))

        payload = to_ocs_response(result)

        # 校验错误响应结构与状态
        self.assertEqual(payload["code"], 1)
        self.assertIsNone(payload["data"]["answer"])
        self.assertTrue(payload["data"]["ai"]["review_required"])
        self.assertEqual(payload["data"]["ai"]["error_code"], "INVALID_REQUEST")

    def test_judgement_response_uses_clickable_text_answer(self) -> None:
        """测试判断题对 OCS 返回对/错文本，而不是内部 A/B 标签。"""
        result = QueryResult(
            ok=True,
            query=QuestionQuery(title="判断题(1分)示例判断题。", question_type="judgement"),
            candidate_answer="A",
            answer_text="对",
            explanation="示例解析",
            confidence=0.99,
            resolution_mode="ai_cache",
            review_required=False,
        )

        payload = to_ocs_response(result)

        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["answer"], "对")
        self.assertEqual(payload["data"]["answer_raw"], "A")

    def test_judgement_response_falls_back_from_label_to_text(self) -> None:
        """测试判断题缺少 answer_text 时也能把 B 转成错。"""
        result = QueryResult(
            ok=True,
            query=QuestionQuery(title="判断题(1分)示例错误判断题。", question_type="judgement"),
            candidate_answer="B",
            answer_text=None,
            explanation="示例解析",
            confidence=0.99,
            resolution_mode="llm_fallback",
            review_required=True,
        )

        payload = to_ocs_response(result)

        self.assertEqual(payload["data"]["answer"], "错")
        self.assertEqual(payload["data"]["answer_raw"], "B")

    def test_completion_response_falls_back_to_answer_text(self) -> None:
        """测试填空题没有 candidate_answer 时，OCS 仍能拿到 answer_text。"""
        result = QueryResult(
            ok=True,
            query=QuestionQuery(title="填空题(1分)示例。", question_type="completion"),
            candidate_answer=None,
            answer_text="南方谈话",
            explanation="示例解析",
            confidence=0.96,
            resolution_mode="llm_fallback",
            review_required=True,
        )

        payload = to_ocs_response(result)

        self.assertEqual(payload["data"]["answer"], "南方谈话")
        self.assertIsNone(payload["data"]["answer_raw"])

    def test_multi_blank_completion_response_keeps_json_array_string(self) -> None:
        """测试多空填空会保留 OCS 可解析的 JSON 数组字符串。"""
        result = QueryResult(
            ok=True,
            query=QuestionQuery(title="填空题(2分)双空示例。", question_type="completion"),
            candidate_answer='["第一空答案", "第二空答案"]',
            answer_text="第一空答案；第二空答案",
            explanation="示例解析",
            confidence=0.97,
            resolution_mode="llm_fallback",
            review_required=True,
        )

        payload = to_ocs_response(result)

        self.assertEqual(payload["data"]["answer"], '["第一空答案", "第二空答案"]')
        self.assertEqual(payload["data"]["answer_raw"], '["第一空答案", "第二空答案"]')


def _cmmlu_index() -> LocalQuestionIndex:
    """初始化用于测试的 CMMLU 题库本地索引。

    Returns:
        LocalQuestionIndex: 包含解剖学分类数据的本地内存索引对象。
    """
    source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"
    return LocalQuestionIndex(tuple(iter_cmmlu_records(source_path)))


if __name__ == "__main__":
    unittest.main()
