"""OpenAI Images 协议适配器的无网络回归测试。"""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from study_qb_assistant.llm.http_client import HttpClientError
from study_qb_assistant.llm.image_generation import (
    ImageGenerationProviderError,
    ImageGenerationRequest,
    OpenAIChatImageGenerationProvider,
    OpenAIImageGenerationProvider,
)
from study_qb_assistant.platform.image_generation.records import ImageGenerationModelRecord
from study_qb_assistant.platform.image_generation.service import build_image_generation_provider


class OpenAIImageGenerationProviderTests(unittest.TestCase):
    """验证供应商响应在进入资产层前已被规范化且不泄露临时 URL。"""

    def setUp(self) -> None:
        """构建固定配置，避免测试依赖运行时系统配置。"""

        self.provider = OpenAIImageGenerationProvider(
            base_url="https://images.example.test/v1",
            model="test-image-model",
            api_key="test-secret-key",
            timeout_seconds=30,
        )
        self.request = ImageGenerationRequest(
            prompt="蓝色几何方块", size="1024x1024", request_id="test-request"
        )

    def test_base64_response_uses_openai_images_contract(self) -> None:
        """Base64 响应应被转换为字节流，并使用正确的 Images 请求形状。"""

        content = b"test-image-content"
        response_body = json.dumps(
            {
                "id": "provider-request-1",
                "data": [{"b64_json": base64.b64encode(content).decode("ascii")}],
            }
        )
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            return_value=response_body,
        ) as request_text:
            result = self.provider.generate(self.request)

        self.assertEqual(result.content, content)
        self.assertEqual(result.provider_request_id, "provider-request-1")
        _, url = request_text.call_args.args[:2]
        self.assertEqual(url, "https://images.example.test/v1/images/generations")
        self.assertEqual(request_text.call_args.kwargs["headers"]["Authorization"], "Bearer test-secret-key")
        payload = request_text.call_args.kwargs["json_body"]
        self.assertEqual(payload["response_format"], "b64_json")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(payload["model"], "test-image-model")

    def test_temporary_url_is_downloaded_server_side(self) -> None:
        """供应商 URL 只能在服务端读取，调用方最终只得到图片字节。"""

        response_body = json.dumps(
            {
                "id": "provider-request-2",
                "data": [{"url": "https://cdn.example.test/generated.png"}],
            }
        )
        with (
            patch(
                "study_qb_assistant.llm.image_generation.openai_images.request_text",
                return_value=response_body,
            ),
            patch(
                "study_qb_assistant.llm.image_generation.openai_images.is_public_http_url",
                return_value=True,
            ),
            patch(
                "study_qb_assistant.llm.image_generation.openai_images.request_bytes",
                return_value=(b"downloaded-image", "image/png"),
            ) as request_bytes,
        ):
            result = self.provider.generate(self.request)

        self.assertEqual(result.content, b"downloaded-image")
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(request_bytes.call_args.args[1], "https://cdn.example.test/generated.png")
        self.assertNotIn("cdn.example.test", repr(result))

    def test_rejected_or_invalid_responses_return_safe_errors(self) -> None:
        """内容策略与不安全临时 URL 不应向上游调用方泄露原始细节。"""

        policy_body = json.dumps({"error": {"message": "content policy violation"}})
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            return_value=policy_body,
        ):
            with self.assertRaises(ImageGenerationProviderError) as policy_error:
                self.provider.generate(self.request)
        self.assertEqual(policy_error.exception.code, "CONTENT_POLICY_REJECTED")
        self.assertEqual(policy_error.exception.message, "图片描述不符合生图服务的内容规范")

        unsafe_url_body = json.dumps({"data": [{"url": "http://127.0.0.1/private.png"}]})
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            return_value=unsafe_url_body,
        ):
            with self.assertRaises(ImageGenerationProviderError) as unsafe_error:
                self.provider.generate(self.request)
        self.assertEqual(unsafe_error.exception.code, "PROVIDER_INVALID_RESPONSE")
        self.assertEqual(unsafe_error.exception.message, "生图服务返回了不安全的图片地址")

    def test_unsupported_model_error_is_actionable_even_when_gateway_uses_500(self) -> None:
        """网关把协议不兼容包装成 500 时，管理端仍应得到可配置的错误分类。"""

        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            side_effect=HttpClientError(
                "HTTP 500: Internal Server Error",
                status_code=500,
                response_body="not supported model for image generation",
            ),
        ):
            with self.assertRaises(ImageGenerationProviderError) as error:
                self.provider.generate(self.request)

        self.assertEqual(error.exception.code, "PROVIDER_REJECTED")
        self.assertEqual(error.exception.message, "生图模型或调用协议不受当前服务支持")


class OpenAIChatImageGenerationProviderTests(unittest.TestCase):
    """验证聊天补全协议生成的图片可复用同一资产校验链路。"""

    def setUp(self) -> None:
        """构建不会触达真实网关的聊天生图适配器。"""

        self.provider = OpenAIChatImageGenerationProvider(
            base_url="https://images.example.test/v1",
            model="test-chat-image-model",
            api_key="test-secret-key",
            timeout_seconds=30,
        )
        self.request = ImageGenerationRequest(
            prompt="橙色纸飞机", size="1024x1024", request_id="test-chat-request"
        )

    def test_markdown_data_url_response_is_decoded_with_original_mime_type(self) -> None:
        """兼容网关用 Markdown 返回 data URL 时应保留 JPEG MIME。"""

        content = b"chat-image-content"
        response_body = json.dumps(
            {
                "id": "chat-request-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "已生成：![image](data:image/jpeg;base64,"
                                f"{base64.b64encode(content).decode('ascii')})"
                            ),
                        }
                    }
                ],
            }
        )
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            return_value=response_body,
        ) as request_text:
            result = self.provider.generate(self.request)

        self.assertEqual(result.content, content)
        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.provider_request_id, "chat-request-1")
        _, url = request_text.call_args.args[:2]
        self.assertEqual(url, "https://images.example.test/v1/chat/completions")
        payload = request_text.call_args.kwargs["json_body"]
        self.assertEqual(payload["modalities"], ["text", "image"])
        self.assertFalse(payload["stream"])
        self.assertNotIn("size", payload)

    def test_missing_chat_image_returns_safe_error(self) -> None:
        """纯文本聊天响应不能被误当作成功生图。"""

        response_body = json.dumps(
            {"choices": [{"message": {"content": "暂时无法生成图片"}}]}
        )
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text",
            return_value=response_body,
        ):
            with self.assertRaises(ImageGenerationProviderError) as error:
                self.provider.generate(self.request)

        self.assertEqual(error.exception.code, "PROVIDER_INVALID_RESPONSE")

    def test_provider_factory_selects_protocol_without_model_name_branching(self) -> None:
        """调用协议应由配置选择，不应根据模型名称做硬编码判断。"""

        record = ImageGenerationModelRecord(
            model_id="chat-image-model",
            name="测试聊天生图",
            provider="openai-chat-image",
            base_url="https://images.example.test/v1",
            model="any-compatible-chat-image-model",
            api_key="test-secret-key",
            timeout_seconds=30,
            status="active",
            capabilities="text-to-image,1024x1024",
            created_at=0,
            updated_at=0,
        )

        self.assertIsInstance(
            build_image_generation_provider(record), OpenAIChatImageGenerationProvider
        )


if __name__ == "__main__":
    unittest.main()
