"""OpenAI Images 协议的文本生图适配器。"""

from __future__ import annotations

import binascii
import base64
import io
import json
from dataclasses import dataclass
from typing import Any

from PIL import Image

from ..http_client import (
    HttpClientError,
    normalize_container_loopback_url,
    request_multipart_text,
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

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "size": request.size,
            "n": 1,
            "response_format": "b64_json",
        }
        if request.input_images or request.mask_image:
            response = self._post_multipart_edit(request, payload)
        else:
            response = self._post_json(
                payload,
                endpoint="images/generations",
                request=request,
            )
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

    def _post_multipart_edit(
        self, request: ImageGenerationRequest, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """以官方 Images edits 的 multipart 形态提交主图、参考图和可选蒙版。"""

        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for index, asset in enumerate(request.input_images):
            extension = mime_extension(asset.mime_type)
            files.append(
                (
                    "image",
                    (f"{asset.role or 'image'}-{index}.{extension}", asset.content, asset.mime_type),
                )
            )
        if request.mask_image is not None:
            files.append(
                (
                    "mask",
                    ("mask.png", openai_alpha_mask(request.mask_image.content), "image/png"),
                )
            )
        if not files:
            raise ImageGenerationProviderError("IMAGE_EDIT_UNSUPPORTED", "当前请求缺少编辑图片")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        form_data = {key: str(value) for key, value in payload.items()}
        request.notify_provider_dispatch()
        try:
            body = request_multipart_text(
                "POST",
                f"{self.base_url.rstrip('/')}/images/edits",
                headers=headers,
                data=form_data,
                files=files,
                timeout=self.timeout_seconds,
                proxy_env="STQB_LLM_PROXY",
            )
        except HttpClientError as exc:
            raise self._provider_error(exc) from exc
        return self._decode_response(body)

    def _post_json(
        self,
        payload: dict[str, Any],
        *,
        endpoint: str = "images/generations",
        request: ImageGenerationRequest | None = None,
    ) -> dict[str, Any]:
        """向兼容 OpenAI 的指定端点提交 JSON 请求并解析响应。"""

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if request is not None:
            request.notify_provider_dispatch()
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
            raise self._provider_error(exc) from exc
        return self._decode_response(body)

    @staticmethod
    def _decode_response(body: str) -> dict[str, Any]:
        """解码 Images API 统一 JSON 响应。"""
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

    @staticmethod
    def _provider_error(exc: HttpClientError) -> ImageGenerationProviderError:
        """将 HTTP 失败映射为不泄露网关细节的稳定业务错误。"""

        detail = str(exc)
        lowered = f"{detail} {exc.response_body}".lower()
        if any(marker in lowered for marker in ("content policy", "safety", "moderation")):
            return ImageGenerationProviderError(
                "CONTENT_POLICY_REJECTED", "图片描述不符合生图服务的内容规范"
            )
        if any(
            marker in lowered
            for marker in (
                "not supported model",
                "unsupported model",
                "unsupported endpoint",
                "only imagen models",
            )
        ):
            return ImageGenerationProviderError(
                "PROVIDER_REJECTED", "生图模型或调用协议不受当前服务支持"
            )
        if "timeout" in lowered or exc.status_code in {408, 504}:
            return ImageGenerationProviderError("PROVIDER_TIMEOUT", "生图服务响应超时")
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            return ImageGenerationProviderError("PROVIDER_REJECTED", "生图服务拒绝了当前请求")
        return ImageGenerationProviderError("PROVIDER_UNAVAILABLE", "生图服务暂时不可用")

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
                redirect_validator=is_public_http_url,
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


def mime_extension(mime_type: str) -> str:
    """为 multipart 文件名选择安全的扩展名。"""

    return {"image/jpeg": "jpg", "image/webp": "webp"}.get(mime_type, "png")


def openai_alpha_mask(content: bytes) -> bytes:
    """把系统的白色编辑区域蒙版转换为 OpenAI 所需的透明编辑区域。"""

    try:
        with Image.open(io.BytesIO(content)) as source:
            luminance = source.convert("L")
            alpha = luminance.point(lambda value: 0 if value >= 128 else 255)
            rgba = Image.new("RGBA", source.size, (0, 0, 0, 255))
            rgba.putalpha(alpha)
            buffer = io.BytesIO()
            rgba.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except OSError as exc:
        raise ImageGenerationProviderError("INVALID_MASK_IMAGE", "蒙版图片无法用于编辑") from exc
