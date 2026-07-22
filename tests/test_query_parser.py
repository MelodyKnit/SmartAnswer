"""查询请求解析与图片上下文清洗测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.questions.parsing import (  # noqa: E402
    QueryInputError,
    build_query_from_payload,
    parse_pasted_question_text,
)
from study_qb_assistant.api.contracts.query import QueryPayload  # noqa: E402
from study_qb_assistant.media.inputs import (  # noqa: E402
    normalize_image_data_urls,
    normalize_image_urls,
)


class QueryParserTests(unittest.TestCase):
    """验证查询输入解析、图片上下文与清洗行为。"""

    def test_raw_text_extracts_terminal_labeled_options(self) -> None:
        """单输入框应从末尾连续标准选项行中提取题干与选项。"""

        query = build_query_from_payload(
            QueryPayload(
                raw_text="\n".join(
                    (
                        "多选题：下列哪些属于示例？",
                        "A. 正确项",
                        "B、另一个正确项",
                        "C）干扰项",
                        "(D) 另一干扰项",
                    )
                )
            )
        )

        self.assertEqual(query.title, "多选题：下列哪些属于示例？")
        self.assertEqual(
            query.options,
            ("A. 正确项", "B、另一个正确项", "C）干扰项", "(D) 另一干扰项"),
        )
        self.assertEqual(query.question_type, "multiple")

    def test_raw_text_preserves_unrecognized_lines_as_title(self) -> None:
        """无法确认选项结构时，原文必须完整进入题干而不是被误拆。"""

        raw_text = "题干内容\n第一项\n第二项\n第三项"
        parsed = parse_pasted_question_text(raw_text)
        query = build_query_from_payload(QueryPayload(raw_text=raw_text))

        self.assertEqual(parsed.title, raw_text)
        self.assertEqual(query.title, "题干内容第一项第二项第三项")
        self.assertEqual(query.options, ())
        self.assertEqual(query.question_type, "unknown")

    def test_raw_text_never_infers_choice_type_from_option_count(self) -> None:
        """四个选项不等同于单选，未标注题型时必须保持 unknown。"""

        query = build_query_from_payload(
            QueryPayload(raw_text="题干内容\nA. 第一项\nB. 第二项\nC. 第三项\nD. 第四项")
        )

        self.assertEqual(query.options, ("A. 第一项", "B. 第二项", "C. 第三项", "D. 第四项"))
        self.assertEqual(query.question_type, "unknown")

    def test_raw_text_with_only_options_is_not_converted_to_an_empty_stem(self) -> None:
        """缺少题干的选项文本应原样保留，不能生成空题干查询。"""

        raw_text = "A. 第一项\nB. 第二项"
        query = build_query_from_payload(QueryPayload(raw_text=raw_text))

        self.assertEqual(query.title, "A. 第一项 B. 第二项")
        self.assertEqual(query.options, ())

    def test_raw_text_explicit_type_overrides_inferred_type(self) -> None:
        """高级设置指定题型时必须优先于文本中的自动识别结果。"""

        query = build_query_from_payload(
            QueryPayload(raw_text="多选题：示例题\nA. 第一项\nB. 第二项", type="single")
        )

        self.assertEqual(query.question_type, "single")

    def test_raw_text_rejects_structured_title_or_options(self) -> None:
        """同一请求不能同时提供两种题目来源，避免检索语义不明确。"""

        with self.assertRaisesRegex(QueryInputError, "raw_text"):
            build_query_from_payload(
                QueryPayload(raw_text="示例题", title="另一道题", options=["A. 选项"])
            )

    def test_non_iterable_image_fields_are_ignored(self) -> None:
        """异常标量输入不应导致图片上下文规范化流程崩溃。"""

        self.assertEqual(normalize_image_urls(123, object()), ())
        self.assertEqual(normalize_image_data_urls(123, object()), ())

    def test_embedded_image_url_is_removed_from_title_when_image_context_exists(self) -> None:
        payload = QueryPayload(
            title="函数https://p.cldisk.com/star3/origin/demo.png的间断点是",
            type="single",
            options=["A. x=2", "B. x=0"],
            image_urls=["https://p.cldisk.com/star3/origin/demo.png"],
        )

        query = build_query_from_payload(payload)

        self.assertEqual(query.title, "函数的间断点是")
        self.assertEqual(query.image_urls, ("https://p.cldisk.com/star3/origin/demo.png",))

    def test_image_capture_status_fields_are_preserved(self) -> None:
        payload = QueryPayload(
            title="https://p.cldisk.com/star3/origin/demo.png",
            type="single",
            image_urls=["https://p.cldisk.com/star3/origin/demo.png"],
            image_capture_status="url_only_fallback",
            image_capture_failures=2,
        )

        query = build_query_from_payload(payload)

        self.assertEqual(query.image_capture_status, "url_only_fallback")
        self.assertEqual(query.image_capture_failures, 2)

    def test_embedded_image_url_without_spaces_is_inferred_from_title(self) -> None:
        payload = QueryPayload(
            title=(
                "设https://p.ananas.chaoxing.com/star3/origin/demo-a.png"
                "则https://p.ananas.chaoxing.com/star3/origin/demo-b.png____、____。"
            ),
            type="completion",
        )

        query = build_query_from_payload(payload)

        self.assertEqual(query.title, "设则____、____。")
        self.assertEqual(
            query.image_urls,
            (
                "https://p.ananas.chaoxing.com/star3/origin/demo-a.png",
                "https://p.ananas.chaoxing.com/star3/origin/demo-b.png",
            ),
        )

    def test_concatenated_embedded_image_urls_are_parsed_separately_and_correctly(self) -> None:
        """无空格直接拼接的密恐 URL 题干应能被降解识别为多个独立 clean 链接，且不会包含畸形的整体链接。"""
        payload = QueryPayload(
            title=(
                "https://p.ananas.chaoxing.com/star3/origin/660b02b21b1d078069a1421db947a7b.png"
                "https://p.ananas.chaoxing.com/star3/origin/3005a2bfc7b2f6b48b189987f0e6e5e.png"
            ),
            type="single",
        )

        query = build_query_from_payload(payload)

        self.assertEqual(query.title, "")
        self.assertEqual(
            query.image_urls,
            (
                "https://p.ananas.chaoxing.com/star3/origin/660b02b21b1d078069a1421db947a7b.png",
                "https://p.ananas.chaoxing.com/star3/origin/3005a2bfc7b2f6b48b189987f0e6e5e.png",
            ),
        )


if __name__ == "__main__":
    unittest.main()
