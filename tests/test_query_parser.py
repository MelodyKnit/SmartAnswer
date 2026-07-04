"""查询请求解析与图片上下文清洗测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.query_parser import build_query_from_payload  # noqa: E402
from study_qb_assistant.api.schemas import QueryPayload  # noqa: E402


class QueryParserTests(unittest.TestCase):
    """验证图片上下文不会污染题干与抓图状态字段。"""

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


if __name__ == "__main__":
    unittest.main()
