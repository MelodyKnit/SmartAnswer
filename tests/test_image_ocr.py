"""图片题补强链路测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.image_ocr import (  # noqa: E402
    CHAOXING_IMAGE_REFERER,
    browser_image_request_headers,
    build_model_query,
)
from study_qb_assistant.models import QuestionQuery  # noqa: E402


class FakeImageResponse:
    """模拟 httpx 图片响应。"""

    def __init__(self, content: bytes, content_type: str = "image/jpg") -> None:
        self.content = content
        self.headers = {"content-type": content_type}

    def __enter__(self) -> "FakeImageResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self):
        yield self.content


class ImageOcrHydrationTests(unittest.TestCase):
    """覆盖 URL 图片转内联 data URL 的关键行为。"""

    def test_p_cldisk_image_uses_chaoxing_referer_by_default(self) -> None:
        headers = browser_image_request_headers(
            "https://p.cldisk.com/star3/origin/demo-question.jpg"
        )

        self.assertEqual(headers["Referer"], CHAOXING_IMAGE_REFERER)
        self.assertIn("image/", headers["Accept"])
        self.assertIn("Mozilla", headers["User-Agent"])

    def test_page_url_referer_has_priority_over_domain_default(self) -> None:
        headers = browser_image_request_headers(
            "https://p.cldisk.com/star3/origin/demo-question.jpg",
            referer="https://mooc1.chaoxing.com/work/do-homework",
        )

        self.assertEqual(headers["Referer"], "https://mooc1.chaoxing.com/work/do-homework")

    def test_build_model_query_hydrates_url_only_image_to_data_url(self) -> None:
        captured: dict[str, object] = {}

        def fake_stream(*args: object, **kwargs: object) -> FakeImageResponse:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return FakeImageResponse(b"\xff\xd8fake-jpeg")

        query = QuestionQuery(
            title="https://p.cldisk.com/star3/origin/demo-question.jpg",
            question_type="single",
            request_id="req-image-1",
            page_url="https://mooc1.chaoxing.com/work/do-homework",
            image_urls=("https://p.cldisk.com/star3/origin/demo-question.jpg",),
        )

        with (
            patch("study_qb_assistant.image_ocr.is_public_http_url", return_value=True),
            patch("study_qb_assistant.image_ocr.httpx.stream", side_effect=fake_stream),
            patch("study_qb_assistant.image_ocr.log_event") as log_event,
        ):
            hydrated = build_model_query(query)

        self.assertEqual(hydrated.title, query.title)
        self.assertEqual(hydrated.question_type, "single")
        self.assertEqual(hydrated.request_id, "req-image-1")
        self.assertEqual(hydrated.page_url, query.page_url)
        self.assertEqual(hydrated.image_urls, query.image_urls)
        self.assertEqual(len(hydrated.image_data_urls), 1)
        self.assertTrue(hydrated.image_data_urls[0].startswith("data:image/jpg;base64,"))
        headers = captured["kwargs"]["headers"]  # type: ignore[index]
        self.assertIn("image/", headers["Accept"])
        self.assertEqual(headers["Referer"], query.page_url)
        log_event.assert_any_call(
            "image_hydration",
            {
                "request_id": "req-image-1",
                "domain": "p.cldisk.com",
                "method": "httpx_browser_headers",
                "ok": True,
                "reason": "",
                "mime_type": "image/jpg",
                "byte_count": len(b"\xff\xd8fake-jpeg"),
            },
        )

    def test_existing_data_url_does_not_trigger_server_fetch(self) -> None:
        query = QuestionQuery(
            title="图片题",
            question_type="single",
            image_urls=("https://p.cldisk.com/star3/origin/demo-question.jpg",),
            image_data_urls=("data:image/png;base64,AA==",),
        )

        with patch("study_qb_assistant.image_ocr.fetch_public_image_asset") as fetch_asset:
            hydrated = build_model_query(query)

        self.assertIs(hydrated, query)
        fetch_asset.assert_not_called()

    def test_private_image_url_is_rejected_before_http_fetch(self) -> None:
        stream = Mock()
        query = QuestionQuery(
            title="http://127.0.0.1/private.jpg",
            question_type="single",
            image_urls=("http://127.0.0.1/private.jpg",),
        )

        with (
            patch("study_qb_assistant.image_ocr.httpx.stream", stream),
            patch(
                "study_qb_assistant.image_ocr.fetch_image_via_playwright", return_value=(None, None)
            ),
            patch("study_qb_assistant.image_ocr.log_event"),
        ):
            hydrated = build_model_query(query)

        self.assertEqual(hydrated.image_data_urls, ())
        stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
