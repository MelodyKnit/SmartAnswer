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

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.providers.openai_compatible import (  # noqa: E402
    OpenAICompatibleProvider,
    _decode_chat_response,
)
from study_qb_assistant.models import QuestionQuery  # noqa: E402
from study_qb_assistant.api.local_server import _split_options  # noqa: E402


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
        options = _split_options(
            '点击上传x#window.UEDITOR_CONFIG.initialFrameWidth = 730;#'
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


if __name__ == "__main__":
    unittest.main()
