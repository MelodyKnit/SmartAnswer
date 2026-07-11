"""大模型提示词模板加载与 provider 接入测试。"""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.llm.prompts import render_prompt  # noqa: E402
from study_qb_assistant.llm.providers.openai_compatible import (  # noqa: E402
    OpenAICompatibleProvider,
)
from study_qb_assistant.models import QuestionQuery  # noqa: E402


class PromptTemplateTests(unittest.TestCase):
    """验证 Jinja 提示词模板的基础契约。"""

    def test_answer_user_template_renders_required_blocks(self) -> None:
        """答题用户模板应能渲染题干、选项、证据和上一轮答案。"""

        prompt = render_prompt(
            "answer_user.jinja",
            question_type="single",
            title="测试题干",
            options_block="A. 正确\nB. 错误",
            format_instructions="Return candidate_answer as exactly one option letter.",
            evidence_block="[1] 来源：证据",
            previous_answer_block="candidate_answer: A",
        )

        self.assertIn("Question type: single", prompt)
        self.assertIn("Question: 测试题干", prompt)
        self.assertIn("Options:", prompt)
        self.assertIn("Output format for this question:", prompt)
        self.assertIn("Web evidence:", prompt)
        self.assertIn("Previous answer:", prompt)

    def test_missing_prompt_variable_fails_loudly(self) -> None:
        """模板变量缺失时应直接失败，避免发送残缺提示词。"""

        with self.assertRaises(RuntimeError):
            render_prompt("answer_user.jinja", question_type="single")

    def test_openai_provider_uses_jinja_prompts_in_payload(self) -> None:
        """OpenAI 兼容 provider 构造 payload 时应使用外部 Jinja 模板。"""

        captured: dict = {}

        def fake_post(_url: str, payload: dict) -> dict:
            captured.update(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "candidate_answer": "A",
                                    "answer_text": "正确项",
                                    "explanation": "模板测试。",
                                    "confidence": 0.99,
                                    "question_form": "choice",
                                    "reuse_policy": "reusable",
                                    "reuse_reason": "确定性题目",
                                    "reuse_confidence": 0.99,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        provider = OpenAICompatibleProvider(
            base_url="http://example.test/v1",
            model="mock-model",
            stream=False,
        )
        with patch.object(OpenAICompatibleProvider, "_post_json", side_effect=fake_post):
            answer = provider.answer(
                QuestionQuery(
                    title="模板测试题",
                    options=("正确项", "干扰项"),
                    question_type="single",
                )
            )

        self.assertEqual(answer.candidate_answer, "A")
        system_prompt = captured["messages"][0]["content"]
        user_prompt = captured["messages"][1]["content"]
        self.assertIn("Return only JSON", system_prompt)
        self.assertIn("Question: 模板测试题", user_prompt)
        self.assertIn("A. 正确项", user_prompt)
        self.assertIn("Return candidate_answer as exactly one option letter", user_prompt)

    def test_openai_provider_sends_mixed_image_refs_in_payload(self) -> None:
        """多模态 payload 应同时保留 data URL 和公开图片 URL。"""

        captured: dict = {}

        def fake_post(_url: str, payload: dict) -> dict:
            captured.update(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "candidate_answer": "A",
                                    "answer_text": "图片选项",
                                    "explanation": "图片引用测试。",
                                    "confidence": 0.9,
                                    "question_form": "choice",
                                    "reuse_policy": "reusable",
                                    "reuse_reason": "确定性题目",
                                    "reuse_confidence": 0.9,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        data_url = "data:image/png;base64," + base64.b64encode(b"stem").decode("ascii")
        image_url = "https://cdn.example.com/option-a.png"
        provider = OpenAICompatibleProvider(
            base_url="http://example.test/v1",
            model="mock-model",
            stream=False,
        )
        with patch.object(OpenAICompatibleProvider, "_post_json", side_effect=fake_post):
            provider.answer(
                QuestionQuery(
                    title="图片题",
                    image_data_urls=(data_url,),
                    option_image_urls={"A": image_url},
                    question_type="single",
                )
            )

        user_content = captured["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(
            [part["image_url"]["url"] for part in user_content[1:]],
            [data_url, image_url],
        )


if __name__ == "__main__":
    unittest.main()
