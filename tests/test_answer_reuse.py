"""AI 答案复用策略的边界测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.answer_reuse import (  # noqa: E402
    REUSE_POLICY_NON_REUSABLE_OPEN_TEXT,
    REUSE_POLICY_REUSABLE,
    decide_answer_reuse,
)
from study_qb_assistant.models import QuestionQuery  # noqa: E402


class AnswerReusePolicyTests(unittest.TestCase):
    """验证开放性长文本题与普通确定性题的复用边界。"""

    def test_open_text_generation_is_not_reusable(self) -> None:
        """带明确写作任务和字数约束的开放题不应进入自动复用链路。"""
        query = QuestionQuery(
            title="请围绕新时代青年责任写一篇不少于800字的作文",
            question_type="completion",
        )

        decision = decide_answer_reuse(
            query,
            answer_text="新时代青年责任：" + "青年应在学习、实践和服务社会中承担责任。" * 12,
        )

        self.assertEqual(decision.policy, REUSE_POLICY_NON_REUSABLE_OPEN_TEXT)
        self.assertFalse(decision.reusable)

    def test_model_reuse_policy_marks_open_text_as_not_reusable(self) -> None:
        """模型明确标记开放题时，应按不可复用处理。"""
        query = QuestionQuery(
            title="写一篇关于人工智能学习体验的短文",
            question_type="completion",
        )

        decision = decide_answer_reuse(
            query,
            answer_text="人工智能学习体验：" + "学习过程让我理解了工具和方法的关系。" * 12,
            reuse_policy=REUSE_POLICY_NON_REUSABLE_OPEN_TEXT,
            question_form="open_text_generation",
            reuse_reason="personalized writing task",
            reuse_confidence=0.95,
        )

        self.assertEqual(decision.policy, REUSE_POLICY_NON_REUSABLE_OPEN_TEXT)
        self.assertEqual(decision.reason, "personalized writing task")

    def test_open_text_nouns_in_deterministic_question_remain_reusable(self) -> None:
        """作文、报告等词作为普通名词出现时，不能误判为开放性写作题。"""
        query = QuestionQuery(
            title="小明写了五篇作文，小红写了十篇作文，两人加一起一共几篇？",
            question_type="completion",
        )

        decision = decide_answer_reuse(
            query,
            answer_text="15篇",
            reuse_policy=REUSE_POLICY_REUSABLE,
            question_form="deterministic_calculation",
            reuse_confidence=0.95,
        )

        self.assertEqual(decision.policy, REUSE_POLICY_REUSABLE)
        self.assertTrue(decision.reusable)

    def test_real_blank_completion_remains_reusable(self) -> None:
        """带明确空位的真实填空题应允许复用。"""
        query = QuestionQuery(
            title="填空题(1分)1992年，邓小平发表【1】____，产生重大影响。",
            question_type="completion",
        )

        decision = decide_answer_reuse(
            query,
            answer_text="南方谈话",
            reuse_policy=REUSE_POLICY_NON_REUSABLE_OPEN_TEXT,
            question_form="open_text_generation",
            reuse_confidence=0.95,
        )

        self.assertEqual(decision.policy, REUSE_POLICY_REUSABLE)
        self.assertTrue(decision.reusable)
        self.assertEqual(decision.reason, "explicit_blank_guard")

    def test_low_confidence_model_policy_falls_back_to_shape_rules(self) -> None:
        """模型低可信漏标时，应回落到服务端明显长文本任务兜底规则。"""
        query = QuestionQuery(
            title="操作系统学习总结及心得体会，不少于2000字",
            question_type="completion",
        )

        decision = decide_answer_reuse(
            query,
            answer_text="操作系统学习心得：" + "我理解了进程、内存和文件系统。" * 12,
            reuse_policy=REUSE_POLICY_REUSABLE,
            reuse_confidence=0.2,
        )

        self.assertEqual(decision.policy, REUSE_POLICY_NON_REUSABLE_OPEN_TEXT)
        self.assertFalse(decision.reusable)


if __name__ == "__main__":
    unittest.main()
