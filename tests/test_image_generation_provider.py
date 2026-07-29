"""OpenAI Images 协议适配器的无网络回归测试。"""

from __future__ import annotations

import base64
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

from study_qb_assistant.llm.http_client import HttpClientError
from study_qb_assistant.llm.image_generation import (
    GeminiNativeImageGenerationProvider,
    ImageInputAsset,
    ImageGenerationProviderError,
    ImageGenerationRequest,
    OpenAIChatImageGenerationProvider,
    OpenAIImageGenerationProvider,
)
from study_qb_assistant.platform.image_generation.records import ImageGenerationModelRecord
from study_qb_assistant.platform.image_generation.service import build_image_generation_provider


def png_bytes(*, mode: str = "RGB", size: tuple[int, int] = (2, 1)) -> bytes:
    """构造供协议请求形状测试使用的最小有效图片。"""

    image = Image.new(mode, size, "black")
    if mode == "L":
        image.putpixel((0, 0), 255)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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

    def test_edit_request_uses_private_bytes_and_transparent_openai_mask(self) -> None:
        """OpenAI Images 编辑请求应使用 multipart，白色蒙版区域转换为透明可编辑区域。"""

        callbacks: list[str] = []
        request = ImageGenerationRequest(
            prompt="将主图中的蓝色方块改成红色圆形",
            size="1024x1024",
            request_id="openai-edit-request",
            mode="masked_edit",
            input_images=(
                ImageInputAsset(content=png_bytes(), mime_type="image/png", role="source"),
            ),
            mask_image=ImageInputAsset(
                content=png_bytes(mode="L"), mime_type="image/png", role="mask"
            ),
            on_provider_dispatch=lambda: callbacks.append("sent"),
        )
        response_body = json.dumps(
            {"id": "provider-edit-1", "data": [{"b64_json": base64.b64encode(b"image").decode()}]}
        )
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_multipart_text",
            return_value=response_body,
        ) as request_multipart:
            self.provider.generate(request)

        _, url = request_multipart.call_args.args[:2]
        self.assertEqual(url, "https://images.example.test/v1/images/edits")
        self.assertEqual(callbacks, ["sent"])
        self.assertEqual(request_multipart.call_args.kwargs["data"]["model"], "test-image-model")
        files = request_multipart.call_args.kwargs["files"]
        self.assertEqual([field for field, _value in files], ["image", "mask"])
        mask_content = files[1][1][1]
        with Image.open(io.BytesIO(mask_content)) as mask:
            self.assertEqual(mask.getchannel("A").getpixel((0, 0)), 0)
            self.assertEqual(mask.getchannel("A").getpixel((1, 0)), 255)


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

    def test_chat_protocol_rejects_image_edit_before_network_dispatch(self) -> None:
        """旧聊天协议不能把编辑输入伪装成文本请求发送给上游。"""

        request = ImageGenerationRequest(
            prompt="编辑图片",
            size="model-controlled",
            request_id="chat-edit-request",
            mode="image_edit",
            input_images=(ImageInputAsset(content=png_bytes(), role="source"),),
        )
        with patch(
            "study_qb_assistant.llm.image_generation.openai_images.request_text"
        ) as request_text:
            with self.assertRaises(ImageGenerationProviderError) as error:
                self.provider.generate(request)

        self.assertEqual(error.exception.code, "IMAGE_EDIT_UNSUPPORTED")
        request_text.assert_not_called()

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


class GeminiNativeImageGenerationProviderTests(unittest.TestCase):
    """验证 Gemini 原生协议不依赖 OpenAI 网关的请求字段。"""

    def test_inline_data_response_uses_image_config_and_bearer_auth(self) -> None:
        """Gemini 应传递画幅/像素档位，并读取 candidates 内联图片。"""

        provider = GeminiNativeImageGenerationProvider(
            base_url="https://images.example.test/v1beta",
            model="gemini-image-model",
            api_key="test-secret-key",
            auth_mode="bearer",
        )
        request = ImageGenerationRequest(
            prompt="一只蓝色纸飞机",
            size="16:9 · 2K",
            request_id="gemini-request",
            output_options={"aspect_ratio": "16:9", "image_size": "2K"},
        )
        content = b"gemini-image-content"
        response_body = json.dumps(
            {
                "responseId": "gemini-request-1",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(content).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ],
            }
        )
        with patch(
            "study_qb_assistant.llm.image_generation.gemini_native.request_text",
            return_value=response_body,
        ) as request_text:
            result = provider.generate(request)

        self.assertEqual(result.content, content)
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.provider_request_id, "gemini-request-1")
        _, url = request_text.call_args.args[:2]
        self.assertEqual(
            url,
            "https://images.example.test/v1beta/models/gemini-image-model:generateContent",
        )
        headers = request_text.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer test-secret-key")
        self.assertNotIn("x-goog-api-key", headers)
        payload = request_text.call_args.kwargs["json_body"]
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["TEXT", "IMAGE"])
        self.assertEqual(payload["generationConfig"]["imageConfig"], {"aspectRatio": "16:9", "imageSize": "2K"})

    def test_x_goog_api_key_authentication_is_supported(self) -> None:
        """原生 API Key 鉴权必须使用 x-goog-api-key，而不是拼接到 URL。"""

        provider = GeminiNativeImageGenerationProvider(
            base_url="https://images.example.test/v1beta",
            model="gemini-image-model",
            api_key="test-secret-key",
        )
        response_body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(b"image").decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
        with patch(
            "study_qb_assistant.llm.image_generation.gemini_native.request_text",
            return_value=response_body,
        ) as request_text:
            provider.generate(
                ImageGenerationRequest(prompt="测试", size="1:1 · 1K", request_id="gemini-key")
            )

        headers = request_text.call_args.kwargs["headers"]
        self.assertEqual(headers["x-goog-api-key"], "test-secret-key")
        self.assertNotIn("Authorization", headers)

    def test_edit_request_includes_private_source_mask_and_dispatch_boundary(self) -> None:
        """Gemini 编辑请求以 inlineData 携带私有输入，且在 HTTP 前通知结算边界。"""

        provider = GeminiNativeImageGenerationProvider(
            base_url="https://images.example.test/v1beta",
            model="gemini-image-model",
            api_key="test-secret-key",
        )
        source = png_bytes()
        mask = png_bytes(mode="L")
        callbacks: list[str] = []
        request = ImageGenerationRequest(
            prompt="只修改白色蒙版区域",
            size="1:1 · 1K",
            request_id="gemini-edit-request",
            mode="masked_edit",
            input_images=(ImageInputAsset(content=source, mime_type="image/png", role="source"),),
            mask_image=ImageInputAsset(content=mask, mime_type="image/png", role="mask"),
            on_provider_dispatch=lambda: callbacks.append("sent"),
        )
        response_body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(b"image").decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
        with patch(
            "study_qb_assistant.llm.image_generation.gemini_native.request_text",
            return_value=response_body,
        ) as request_text:
            provider.generate(request)

        self.assertEqual(callbacks, ["sent"])
        parts = request_text.call_args.kwargs["json_body"]["contents"][0]["parts"]
        inline_data = [part["inlineData"]["data"] for part in parts if "inlineData" in part]
        self.assertEqual(inline_data, [base64.b64encode(source).decode("ascii"), base64.b64encode(mask).decode("ascii")])
        text_parts = [part["text"] for part in parts if "text" in part]
        self.assertTrue(any("白色区域" in text for text in text_parts))

    def test_provider_factory_supports_gemini_and_compatible_images(self) -> None:
        """协议选择只依赖显式配置，不根据模型名称或地址猜测。"""

        gemini_record = ImageGenerationModelRecord(
            model_id="gemini-image-model",
            name="Gemini 生图",
            provider="gemini-native",
            base_url="https://images.example.test/v1beta",
            model="gemini-image-model",
            api_key="test-secret-key",
            timeout_seconds=30,
            status="active",
            capabilities="text-to-image",
            created_at=0,
            updated_at=0,
            protocol_config=json.dumps(
                {
                    "auth_mode": "bearer",
                    "aspect_ratios": ["1:1"],
                    "image_sizes": ["1K"],
                }
            ),
        )
        compatible_record = ImageGenerationModelRecord(
            model_id="compatible-image-model",
            name="兼容生图",
            provider="openai-compatible-images",
            base_url="https://images.example.test/v1",
            model="any-compatible-image-model",
            api_key="test-secret-key",
            timeout_seconds=30,
            status="active",
            capabilities="text-to-image,1024x1024",
            created_at=0,
            updated_at=0,
            protocol_config=json.dumps({"preset_sizes": ["1024x1024"]}),
        )

        self.assertIsInstance(
            build_image_generation_provider(gemini_record),
            GeminiNativeImageGenerationProvider,
        )
        compatible_provider = build_image_generation_provider(compatible_record)
        self.assertIsInstance(compatible_provider, OpenAIImageGenerationProvider)
        self.assertEqual(compatible_provider.provider_name, "openai-compatible-images")


if __name__ == "__main__":
    unittest.main()
