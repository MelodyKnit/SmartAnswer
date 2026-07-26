"""Gemini 原生 ``generateContent`` 文本生图适配器。"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from ..http_client import HttpClientError, normalize_container_loopback_url, request_text
from ...media.generated_images import MAX_GENERATED_IMAGE_BYTES
from .contracts import (
    GeneratedImage,
    ImageGenerationProviderError,
    ImageGenerationRequest,
)
from .openai_images import SUPPORTED_IMAGE_MIME_TYPES


@dataclass(slots=True)
class GeminiNativeImageGenerationProvider:
    """调用 Gemini ``generateContent`` 并读取内联图片数据。"""

    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    auth_mode: str = "x-goog-api-key"
    provider_name: str = "gemini-native"

    def __post_init__(self) -> None:
        """规范容器访问宿主机时的基础地址。"""

        self.base_url = normalize_container_loopback_url(self.base_url)

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        """提交原生生图请求，返回第一张合法的内联图片。"""

        image_config = {
            "aspectRatio": request.output_options.get("aspect_ratio", "1:1"),
            "imageSize": request.output_options.get("image_size", "1K"),
        }
        payload = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": image_config,
            },
        }
        response = self._post_json(payload)
        item = first_inline_image(response)
        content, mime_type = decode_inline_image(item)
        return GeneratedImage(
            content=content,
            mime_type=mime_type,
            width=0,
            height=0,
            provider_request_id=str(response.get("responseId") or response.get("id") or ""),
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发送请求并将上游错误归一为稳定的业务错误。"""

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            if self.auth_mode == "x-goog-api-key":
                headers["x-goog-api-key"] = self.api_key
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = f"models/{self.model}:generateContent"
        try:
            body = request_text(
                "POST",
                f"{self.base_url.rstrip('/')}/{endpoint}",
                headers=headers,
                json_body=payload,
                timeout=self.timeout_seconds,
                proxy_env="STQB_LLM_PROXY",
            )
        except HttpClientError as exc:
            raise gemini_provider_error(exc) from exc

        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务返回了非 JSON 响应"
            ) from exc
        if not isinstance(value, dict):
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务返回了无效响应结构"
            )
        error = value.get("error")
        if isinstance(error, dict):
            raise gemini_error_payload(error)
        return value


def first_inline_image(response: dict[str, Any]) -> dict[str, Any]:
    """从 Gemini 响应候选项中读取第一张 ``inlineData`` 图片。"""

    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务未返回图片候选结果"
        )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict):
                return inline_data
    raise ImageGenerationProviderError(
        "PROVIDER_INVALID_RESPONSE", "生图服务未返回图片内容"
    )


def decode_inline_image(item: dict[str, Any]) -> tuple[bytes, str]:
    """校验并解码 Gemini 的 Base64 图片，避免把异常内容传入资产层。"""

    encoded = item.get("data")
    if not isinstance(encoded, str) or not encoded.strip():
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务返回的图片编码无效"
        )
    try:
        content = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务返回的图片编码无效"
        ) from exc
    if len(content) > MAX_GENERATED_IMAGE_BYTES:
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务返回的图片超过大小限制"
        )
    mime_type = str(item.get("mimeType") or item.get("mime_type") or "").split(";", 1)[0].strip().lower()
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务返回了不支持的图片格式"
        )
    return content, mime_type


def gemini_provider_error(exc: HttpClientError) -> ImageGenerationProviderError:
    """将网络和 HTTP 错误映射为不泄露上游细节的生图错误。"""

    detail = f"{exc} {exc.response_body}".lower()
    if any(marker in detail for marker in ("content policy", "safety", "moderation")):
        return ImageGenerationProviderError(
            "CONTENT_POLICY_REJECTED", "图片描述不符合生图服务的内容规范"
        )
    if "timeout" in detail or exc.status_code in {408, 504}:
        return ImageGenerationProviderError("PROVIDER_TIMEOUT", "生图服务响应超时")
    if exc.status_code is not None and 400 <= exc.status_code < 500:
        return ImageGenerationProviderError("PROVIDER_REJECTED", "生图服务拒绝了当前请求")
    return ImageGenerationProviderError("PROVIDER_UNAVAILABLE", "生图服务暂时不可用")


def gemini_error_payload(error: dict[str, Any]) -> ImageGenerationProviderError:
    """将 Gemini JSON 错误对象映射为稳定业务错误。"""

    message = str(error.get("message") or "").lower()
    if any(marker in message for marker in ("content policy", "safety", "moderation")):
        return ImageGenerationProviderError(
            "CONTENT_POLICY_REJECTED", "图片描述不符合生图服务的内容规范"
        )
    return ImageGenerationProviderError("PROVIDER_REJECTED", "生图服务拒绝了当前请求")
