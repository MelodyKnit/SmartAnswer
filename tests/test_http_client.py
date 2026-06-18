"""共享 httpx HTTP 客户端助手的单元测试。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.http_client import HttpClientError, get_json, request_text  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
