"""查询请求解析与图片上下文清洗测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.questions.parsing import build_query_from_payload  # noqa: E402
from study_qb_assistant.api.contracts.query import QueryPayload  # noqa: E402
from study_qb_assistant.media.inputs import (  # noqa: E402
    normalize_image_data_urls,
    normalize_image_urls,
)


class QueryParserTests(unittest.TestCase):
    """验证图片上下文不会污染题干与抓图状态字段。"""

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
