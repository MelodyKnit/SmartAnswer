"""与 OpenAI 兼容的提供者响应解析助手函数的单元测试。

本模块主要测试大模型服务返回结果的解析逻辑，包括：
1. 从被 JSON Markdown Fences 围起来的内容中解析 JSON 对象；
2. 从纯文本格式的生成式回答中进行“尽力而为”的正则提取与启发式匹配；
3. 对 SSE 流式传输（Stream）的多数据包内容进行解码拼接；
4. 将大模型可能返回的列表格式选项数组规整化为 OCS 井号拼接规范（如 A#B#C）；
5. 过滤包含 UEditor 网页富文本编辑器配置的网页抓取杂音。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.llm.providers.openai_compatible import (  # noqa: E402
    OpenAICompatibleProvider,
    _decode_chat_response,
)
from study_qb_assistant.http_client import normalize_container_loopback_url  # noqa: E402
from study_qb_assistant.models import ModelAnswer, QuestionQuery  # noqa: E402
from study_qb_assistant.api.query_parser import split_options  # noqa: E402


class ProviderParsingTests(unittest.TestCase):
    """测试模型响应解析模块的测试类。"""

    def test_json_fenced_model_answer_is_parsed(self) -> None:
        """测试能够正确去除 ```json Fences 标记，并从内部字符串解析出 JSON 字典对象。"""
        provider = OpenAICompatibleProvider(base_url="http://127.0.0.1:1/v1", model="demo")

        # 模拟模型输出的内容被包裹在 ```json 中
        answer = provider._parse_model_answer(
            '```json\n{"candidate_answer":"C","answer_text":"3","explanation":"1+2=3","confidence":0.8}\n```'
        )

        self.assertEqual(answer.candidate_answer, "C")
        self.assertEqual(answer.answer_text, "3")
        self.assertEqual(answer.explanation, "1+2=3")
        self.assertEqual(answer.confidence, 0.8)

    def test_plain_text_model_answer_is_parsed_best_effort(self) -> None:
        """测试在模型未返回标准 JSON、只返回纯文本时，“尽力而为”提取出选项的解析逻辑。

        验证在这种场景下，是否默认标记了较低的置信度。
        """
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")

        # 从纯文本中尝试正则匹配提取选项 “B”
        answer = provider._parse_model_answer("答案是 B，因为题干描述对应第二项。")

        self.assertEqual(answer.candidate_answer, "B")
        self.assertEqual(answer.answer_text, "B")
        # 纯文本解析出的置信度不应过高
        self.assertLess(answer.confidence, 0.5)

    def test_container_loopback_model_url_is_rewritten_to_host_alias(self) -> None:
        """测试容器内 loopback 模型地址会自动改写为宿主机别名。"""

        with patch(
            "study_qb_assistant.http_client.is_running_in_container", return_value=True
        ):
            provider = OpenAICompatibleProvider(
                base_url="http://127.0.0.1:3000/v1", model="demo"
            )

        self.assertEqual(provider.base_url, "http://host.docker.internal:3000/v1")

    def test_non_loopback_model_url_is_kept_unchanged(self) -> None:
        """测试外部模型地址不会被错误改写。"""

        with patch(
            "study_qb_assistant.http_client.is_running_in_container", return_value=True
        ):
            provider = OpenAICompatibleProvider(
                base_url="https://api.example.com/v1", model="demo"
            )

        self.assertEqual(provider.base_url, "https://api.example.com/v1")

    def test_container_loopback_url_helper_preserves_credentials_and_port(self) -> None:
        """测试 loopback 地址改写时保留端口与鉴权凭据。"""

        with patch(
            "study_qb_assistant.http_client.is_running_in_container", return_value=True
        ):
            rewritten = normalize_container_loopback_url(
                "http://user:pass@localhost:7890/proxy"
            )

        self.assertEqual(
            rewritten, "http://user:pass@host.docker.internal:7890/proxy"
        )

    def test_streaming_chat_response_is_joined(self) -> None:
        """测试流式传输的 SSE 数据包解码拼接逻辑。

        验证将零碎的 SSE `data: {...}` 流式数据块还原拼接为完整消息的逻辑。
        """
        # 构造一个模拟 of SSE 多行流数据负载
        payload = "\n\n".join(
            (
                'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"content":"{\\"candidate_answer\\":\\""},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"content":"B\\"}"},"finish_reason":"stop"}]}',
                'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":4}}',
                "data: [DONE]",
            )
        )

        decoded = _decode_chat_response(payload)

        # 校验流数据内容拼接后是否得到合规的 JSON 片段
        self.assertEqual(decoded["choices"][0]["message"]["content"], '{"candidate_answer":"B"}')

    def test_option_text_array_is_normalized_to_ocs_multiple_answer(self) -> None:
        """测试在多选题下，大模型返回的列表选项名数组是否能被正确映射为井号拼接的索引字母。

        若模型以具体文字数组形式返回 ["国家富强", "民族振兴", "人民幸福"]，
        适配器应通过在 options 数组中比对，将其转换映射为 "A#B#C"。
        """
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="实现中华民族伟大复兴的中国梦，就是要实现什么？",
            options=("国家富强", "民族振兴", "人民幸福", "国际和平"),
            question_type="multiple",
        )

        answer = provider._parse_model_answer(
            '{"candidate_answer":["国家富强","民族振兴","人民幸福"],'
            '"answer_text":["国家富强","民族振兴","人民幸福"],'
            '"explanation":"常见表述。","confidence":0.99}',
            query,
        )

        # 检查是否成功转换为大写字母索引的井号拼接形式，以及可读文本的分号拼接形式
        self.assertEqual(answer.candidate_answer, "A#B#C")
        self.assertEqual(answer.answer_text, "国家富强；民族振兴；人民幸福")

    def test_multiple_letter_answers_are_sorted_for_ocs(self) -> None:
        """测试多选题字母答案会被规整为按选项顺序升序输出。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="多选题(1分)顺序测试",
            options=("甲", "乙", "丙", "丁"),
            question_type="multiple",
        )

        answer = provider._parse_model_answer(
            '{"candidate_answer":"D#B#A","answer_text":"丁；乙；甲","explanation":"应选D、B、A","confidence":0.91}',
            query,
        )

        self.assertEqual(answer.candidate_answer, "A#B#D")
        self.assertEqual(answer.answer_text, "甲；乙；丁")

    def test_plain_text_multiple_letters_are_normalized(self) -> None:
        """测试模型直接输出 ACDB 文本时，多选标签仍会被标准化。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="多选题(1分)纯文本顺序测试",
            options=("甲", "乙", "丙", "丁"),
            question_type="multiple",
        )

        answer = provider._parse_model_answer("答案是 ACDB", query)

        self.assertEqual(answer.candidate_answer, "A#B#C#D")

    def test_ocs_editor_noise_is_filtered_from_options(self) -> None:
        """测试富文本编辑器杂音过滤函数，验证是否过滤了诸如 `UEDITOR_CONFIG` 或 `UE.getEditor` 干扰项。"""
        # 模拟网页脚本噪音与有效选项混合的情况
        options = split_options(
            "点击上传x#window.UEDITOR_CONFIG.initialFrameWidth = 730;#"
            "var editor1 = UE.getEditor('answerEditor1');#真实选项"
        )

        # 验证过滤逻辑是否只保留了“真实选项”，去除了垃圾脚本与辅助元素
        self.assertEqual(options, ("真实选项",))

    def test_completion_array_answer_is_encoded_for_multi_blank_ocs(self) -> None:
        """测试多空填空答案会被编码成 OCS 可拆分的 JSON 数组字符串。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="填空题(2分)第一空【1】____，第二空【2】____。",
            options=(),
            question_type="completion",
        )

        answer = provider._parse_model_answer(
            '{"candidate_answer":["第一空答案","第二空答案"],'
            '"answer_text":["第一空答案","第二空答案"],'
            '"explanation":"双空填空。","confidence":0.99}',
            query,
        )

        self.assertEqual(answer.candidate_answer, '["第一空答案", "第二空答案"]')
        self.assertEqual(answer.answer_text, "第一空答案；第二空答案")

    def test_open_text_completion_uses_full_answer_text_as_candidate(self) -> None:
        """测试无空位的 completion 开放题使用正文作为可回填答案。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="操作系统学习总结及心得体会，不少于2000字",
            options=(),
            question_type="completion",
        )
        long_answer = "这是一篇完整心得正文。" * 30

        answer = provider._parse_model_answer(
            '{"candidate_answer":"操作系统学习总结及心得体会",'
            f'"answer_text":"{long_answer}",'
            '"explanation":"开放写作题应回填正文。","confidence":0.98}',
            query,
        )

        self.assertEqual(answer.candidate_answer, long_answer)
        self.assertEqual(answer.answer_text, long_answer)

    def test_render_question_uses_public_option_label_helper_without_name_error(self) -> None:
        """测试渲染带选项题目时不会因为旧私有函数名残留而抛出异常。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")
        query = QuestionQuery(
            title="多选题(1分)渲染题干测试",
            options=("A. 甲", "B. 乙", "C. 丙", "D. 丁"),
            question_type="multiple",
        )

        prompt = provider._render_question(query)

        self.assertIn("Question type: multiple", prompt)
        self.assertIn("A. 甲", prompt)
        self.assertIn("D. 丁", prompt)

    def test_verify_answer_with_evidence_returns_structured_answer(self) -> None:
        """测试证据复核接口仍然返回可解析的结构化答案。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")

        def fake_post_json(_self, url: str, payload: dict) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"candidate_answer":"B","answer_text":"经济安全","explanation":"证据复核后确认。","confidence":0.99}'
                        }
                    }
                ]
            }

        with patch.object(OpenAICompatibleProvider, "_post_json", fake_post_json):
            answer = provider.verify_answer_with_evidence(
                QuestionQuery(
                    title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
                    options=("人民安全", "经济安全", "政治安全", "军事安全"),
                    question_type="single",
                ),
                (),
                ModelAnswer("A", "人民安全", "初次回答。", 0.4),
            )

        self.assertEqual(answer.candidate_answer, "B")
        self.assertEqual(answer.answer_text, "经济安全")

    def test_verify_answer_returns_structured_answer_without_evidence(self) -> None:
        """测试无证据自检接口仍然返回可解析的结构化答案。"""
        provider = OpenAICompatibleProvider(base_url="http://example.test/v1", model="mock")

        def fake_post_json(_self, url: str, payload: dict) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"candidate_answer":"C","answer_text":"经济安全","explanation":"复核后修正。","confidence":0.97}'
                        }
                    }
                ]
            }

        with patch.object(OpenAICompatibleProvider, "_post_json", fake_post_json):
            answer = provider.verify_answer(
                QuestionQuery(
                    title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
                    options=("人民安全", "政治安全", "经济安全", "军事安全"),
                    question_type="single",
                ),
                ModelAnswer("B", "政治安全", "初次回答。", 0.4),
            )

        self.assertEqual(answer.candidate_answer, "C")
        self.assertEqual(answer.answer_text, "经济安全")


if __name__ == "__main__":
    unittest.main()
