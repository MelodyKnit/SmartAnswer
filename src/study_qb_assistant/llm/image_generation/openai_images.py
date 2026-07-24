"""OpenAI Images 协议的文本生图适配器。"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from ..http_client import (
    HttpClientError,
    normalize_container_loopback_url,
    request_bytes,
    request_text,
)
from ...media.generated_images import MAX_GENERATED_IMAGE_BYTES
from ...media.question_context import is_public_http_url
from .contracts import (
    GeneratedImage,
    ImageGenerationProviderError,
    ImageGenerationRequest,
)


SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(slots=True)
class OpenAIImageGenerationProvider:
    """调用兼容 ``/images/generations`` 的文本生图服务。"""

    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    provider_name: str = "openai-images"

    def __post_init__(self) -> None:
        """规范容器访问宿主机时的基础地址。"""

        self.base_url = normalize_container_loopback_url(self.base_url)

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        """调用上游并将 URL 或 Base64 响应规范化为图片字节。"""

        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "size": request.size,
            "n": 1,
            "response_format": "b64_json",
        }
        response = self._post_json(payload)
        data = response.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务返回了无效结果"
            )
        item = data[0]
        content, mime_type = self._read_image(item)
        return GeneratedImage(
            content=content,
            mime_type=mime_type,
            width=0,
            height=0,
            provider_request_id=str(response.get("id") or ""),
            revised_prompt=str(item.get("revised_prompt") or ""),
        )

    def _post_json(
        self, payload: dict[str, Any], *, endpoint: str = "images/generations"
    ) -> dict[str, Any]:
        """向兼容 OpenAI 的指定端点提交 JSON 请求并解析响应。"""

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            body = request_text(
                "POST",
                f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}",
                headers=headers,
                json_body=payload,
                timeout=self.timeout_seconds,
                proxy_env="STQB_LLM_PROXY",
            )
        except HttpClientError as exc:
            detail = str(exc)
            lowered = f"{detail} {exc.response_body}".lower()
            if any(marker in lowered for marker in ("content policy", "safety", "moderation")):
                code = "CONTENT_POLICY_REJECTED"
                message = "图片描述不符合生图服务的内容规范"
            elif any(
                marker in lowered
                for marker in (
                    "not supported model",
                    "unsupported model",
                    "unsupported endpoint",
                    "only imagen models",
                )
            ):
                code = "PROVIDER_REJECTED"
                message = "生图模型或调用协议不受当前服务支持"
            elif "timeout" in lowered or exc.status_code in {408, 504}:
                code = "PROVIDER_TIMEOUT"
                message = "生图服务响应超时"
            elif exc.status_code is not None and 400 <= exc.status_code < 500:
                code = "PROVIDER_REJECTED"
                message = "生图服务拒绝了当前请求"
            else:
                code = "PROVIDER_UNAVAILABLE"
                message = "生图服务暂时不可用"
            raise ImageGenerationProviderError(code, message) from exc

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
            provider_message = str(error.get("message") or "").strip()
            lowered = provider_message.lower()
            code = "CONTENT_POLICY_REJECTED" if any(
                marker in lowered for marker in ("content policy", "safety", "moderation")
            ) else "PROVIDER_REJECTED"
            message = (
                "图片描述不符合生图服务的内容规范"
                if code == "CONTENT_POLICY_REJECTED"
                else "生图服务拒绝了当前请求"
            )
            raise ImageGenerationProviderError(code, message)
        return value

    def _read_image(self, item: dict[str, Any]) -> tuple[bytes, str]:
        """读取 Base64 或临时 URL 图片，绝不向调用方泄露第三方 URL。"""

        encoded = item.get("b64_json")
        if isinstance(encoded, str) and encoded.strip():
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
            mime_type = str(item.get("mime_type") or "image/png").split(";", 1)[0].strip().lower()
            if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
                raise ImageGenerationProviderError(
                    "PROVIDER_INVALID_RESPONSE", "生图服务返回了不支持的图片格式"
                )
            return content, mime_type

        image_url = item.get("url")
        if not isinstance(image_url, str) or not image_url.strip():
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务未返回图片内容"
            )
        if not is_public_http_url(image_url):
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务返回了不安全的图片地址"
            )
        try:
            content, content_type = request_bytes(
                "GET",
                image_url,
                headers={"Accept": "image/png,image/jpeg,image/webp,image/*;q=0.8"},
                timeout=self.timeout_seconds,
                proxy_env="STQB_LLM_PROXY",
                max_bytes=MAX_GENERATED_IMAGE_BYTES,
            )
        except HttpClientError as exc:
            raise ImageGenerationProviderError(
                "PROVIDER_DOWNLOAD_FAILED", "无法读取生图服务返回的图片"
            ) from exc
        mime_type = str(content_type or "").split(";", 1)[0].strip().lower()
        if mime_type and mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ImageGenerationProviderError(
                "PROVIDER_INVALID_RESPONSE", "生图服务返回了不支持的图片格式"
            )
        if not mime_type:
            mime_type = "image/png"
        return content, mime_type
