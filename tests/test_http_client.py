"""共享 httpx HTTP 客户端助手的单元测试。"""

from __future__ import annotations

import os
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.llm.http_client import (  # noqa: E402
    HttpClientError,
    get_json,
    request_bytes,
    request_text,
)


class HttpClientTests(unittest.TestCase):
    """测试共享 HTTP helper 的代理、JSON 和错误转换行为。"""

    def test_request_text_uses_no_proxy_when_unset(self) -> None:
        """未配置代理时，应显式以无代理方式发送请求。"""
        response = httpx.Response(
            200, text="ok", request=httpx.Request("GET", "https://example.test/")
        )

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("httpx.request", return_value=response) as request,
        ):
            text = request_text(
                "GET", "https://example.test/", timeout=1, proxy_env="STQB_SEARCH_PROXY"
            )

        self.assertEqual(text, "ok")
        request.assert_called_once()
        self.assertIsNone(request.call_args.kwargs["proxy"])
        self.assertEqual(request.call_args.kwargs["timeout"], 1)

    def test_request_text_passes_proxy_when_set(self) -> None:
        """配置代理时，应交给 httpx 的 proxy 参数处理。"""
        response = httpx.Response(
            200, text="ok", request=httpx.Request("GET", "https://example.test/")
        )

        with (
            patch.dict(os.environ, {"STQB_SEARCH_PROXY": "http://127.0.0.1:7890"}, clear=True),
            patch("httpx.request", return_value=response) as request,
        ):
            request_text("GET", "https://example.test/", timeout=1, proxy_env="STQB_SEARCH_PROXY")

        self.assertEqual(request.call_args.kwargs["proxy"], "http://127.0.0.1:7890")

    def test_get_json_decodes_response_object(self) -> None:
        """GET JSON helper 应复用 request_text 并返回 JSON 字典。"""
        response = httpx.Response(
            200, text='{"ok": true}', request=httpx.Request("GET", "https://example.test/")
        )

        with patch.dict(os.environ, {}, clear=True), patch("httpx.request", return_value=response):
            payload = get_json("https://example.test/", timeout=1, proxy_env="STQB_SEARCH_PROXY")

        self.assertEqual(payload, {"ok": True})

    def test_request_text_wraps_http_status_errors(self) -> None:
        """HTTP 非 2xx 响应应转换为统一错误，保留状态码和响应体摘要。"""
        response = httpx.Response(
            503,
            text="service down",
            request=httpx.Request("GET", "https://example.test/"),
        )

        with patch.dict(os.environ, {}, clear=True), patch("httpx.request", return_value=response):
            with self.assertRaises(HttpClientError) as raised:
                request_text(
                    "GET", "https://example.test/", timeout=1, proxy_env="STQB_SEARCH_PROXY"
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("service down", str(raised.exception))

    def test_request_bytes_rejects_unsafe_redirect_when_validator_is_provided(self) -> None:
        """临时资源下载应拒绝重定向到私网地址。"""

        response = httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private.png"},
            request=httpx.Request("GET", "https://cdn.example.test/generated.png"),
        )
        with patch("httpx.stream", return_value=nullcontext(response)) as stream:
            with self.assertRaisesRegex(HttpClientError, "Redirect target is not allowed"):
                request_bytes(
                    "GET",
                    "https://cdn.example.test/generated.png",
                    timeout=1,
                    proxy_env="STQB_LLM_PROXY",
                    redirect_validator=lambda target: target.startswith("https://"),
                )

        self.assertEqual(stream.call_count, 1)
        self.assertFalse(stream.call_args.kwargs["follow_redirects"])

    def test_request_bytes_validates_each_redirect_before_downloading_content(self) -> None:
        """允许的 CDN 重定向应在校验后继续读取最终图片内容。"""

        redirect = httpx.Response(
            302,
            headers={"location": "https://images.example.test/final.png"},
            request=httpx.Request("GET", "https://cdn.example.test/generated.png"),
        )
        image = httpx.Response(
            200,
            content=b"image-content",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://images.example.test/final.png"),
        )
        with patch(
            "httpx.stream",
            side_effect=[nullcontext(redirect), nullcontext(image)],
        ) as stream:
            content, content_type = request_bytes(
                "GET",
                "https://cdn.example.test/generated.png",
                timeout=1,
                proxy_env="STQB_LLM_PROXY",
                redirect_validator=lambda target: target.startswith("https://"),
            )

        self.assertEqual(content, b"image-content")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(stream.call_count, 2)
        self.assertEqual(stream.call_args_list[1].args[1], "https://images.example.test/final.png")


if __name__ == "__main__":
    unittest.main()
