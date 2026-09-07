"""图片题补强链路兼容测试。"""

from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.media.question_context import (  # noqa: E402
    CHAOXING_IMAGE_REFERER,
    browser_image_request_headers,
    build_model_query,
    fetch_public_image_with_mime,
)
from study_qb_assistant.questions.models import QuestionQuery  # noqa: E402


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
    """覆盖旧 `image_ocr` 入口下的图片补强关键行为。"""

    def test_p_cldisk_image_uses_chaoxing_referer_by_default(self) -> None:
        headers = browser_image_request_headers(
            "https://p.cldisk.com/star3/origin/demo-question.jpg"
        )

        self.assertEqual(headers["Referer"], CHAOXING_IMAGE_REFERER)
        self.assertIn("image/", headers["Accept"])
        self.assertIn("Mozilla", headers["User-Agent"])

    def test_p_ananas_image_uses_chaoxing_referer_by_default(self) -> None:
        headers = browser_image_request_headers(
            "https://p.ananas.chaoxing.com/star3/origin/demo-question.png"
        )

        self.assertEqual(headers["Referer"], CHAOXING_IMAGE_REFERER)
        self.assertIn("image/", headers["Accept"])

    def test_page_url_referer_has_priority_over_domain_default(self) -> None:
        headers = browser_image_request_headers(
            "https://p.cldisk.com/star3/origin/demo-question.jpg",
            referer="https://mooc1.chaoxing.com/work/do-homework",
        )

        self.assertEqual(headers["Referer"], "https://mooc1.chaoxing.com/work/do-homework")

    def test_build_model_query_hydrates_url_only_image_to_data_url_fallback(self) -> None:
        """未配置公开图床地址时，URL 图片仍应回退为 data URL 给模型使用。"""

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
            patch("study_qb_assistant.media.question_context.is_public_http_url", return_value=True),
            patch("study_qb_assistant.media.question_context.httpx.stream", side_effect=fake_stream),
            patch("study_qb_assistant.media.question_context.log_event") as log_event,
        ):
            hydrated = build_model_query(query)

        self.assertEqual(hydrated.title, "")
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

        with patch("study_qb_assistant.media.question_context.fetch_public_image_asset") as fetch_asset:
            hydrated = build_model_query(query)

        self.assertEqual(hydrated.image_data_urls, query.image_data_urls)
        fetch_asset.assert_not_called()

    def test_private_image_url_is_rejected_before_http_fetch(self) -> None:
        stream = Mock()
        query = QuestionQuery(
            title="http://127.0.0.1/private.jpg",
            question_type="single",
            image_urls=("http://127.0.0.1/private.jpg",),
        )

        with (
            patch("study_qb_assistant.media.question_context.httpx.stream", stream),
            patch(
                "study_qb_assistant.media.question_context.fetch_image_via_playwright",
                return_value=(None, None),
            ),
            patch("study_qb_assistant.media.question_context.log_event"),
        ):
            hydrated = build_model_query(query)

        self.assertEqual(hydrated.image_data_urls, ())
        stream.assert_not_called()

    def test_http_image_fetch_rejects_redirect_to_private_address(self) -> None:
        """公网外链不能通过重定向访问内网地址。"""

        redirect = httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private.png"},
            request=httpx.Request("GET", "https://cdn.example.test/question.png"),
        )
        with (
            patch(
                "study_qb_assistant.media.question_context.is_public_http_url",
                side_effect=[True, False],
            ),
            patch(
                "study_qb_assistant.media.question_context.httpx.stream",
                return_value=nullcontext(redirect),
            ) as stream,
            patch("study_qb_assistant.media.question_context.log_event") as log_event,
        ):
            image, mime_type = fetch_public_image_with_mime(
                "https://cdn.example.test/question.png"
            )

        self.assertIsNone(image)
        self.assertIsNone(mime_type)
        self.assertFalse(stream.call_args.kwargs["follow_redirects"])
        log_event.assert_any_call(
            "image_hydration",
            {
                "request_id": None,
                "domain": "cdn.example.test",
                "method": "httpx_browser_headers",
                "ok": False,
                "reason": "non_public_redirect",
                "mime_type": "",
                "byte_count": 0,
            },
        )

    def test_http_image_fetch_validates_public_redirect_before_reading_image(self) -> None:
        """公网图片的合法重定向仍应保持可用。"""

        redirect = httpx.Response(
            302,
            headers={"location": "https://images.example.test/final.png"},
            request=httpx.Request("GET", "https://cdn.example.test/question.png"),
        )
        image = httpx.Response(
            200,
            content=b"image-content",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://images.example.test/final.png"),
        )
        with (
            patch(
                "study_qb_assistant.media.question_context.is_public_http_url",
                return_value=True,
            ),
            patch(
                "study_qb_assistant.media.question_context.httpx.stream",
                side_effect=[nullcontext(redirect), nullcontext(image)],
            ) as stream,
            patch("study_qb_assistant.media.question_context.log_event"),
        ):
            content, mime_type = fetch_public_image_with_mime(
                "https://cdn.example.test/question.png"
            )

        self.assertEqual(content, b"image-content")
        self.assertEqual(mime_type, "image/png")
        self.assertEqual(stream.call_count, 2)
        self.assertFalse(stream.call_args_list[0].kwargs["follow_redirects"])
        self.assertEqual(stream.call_args_list[1].args[1], "https://images.example.test/final.png")


if __name__ == "__main__":
    unittest.main()
