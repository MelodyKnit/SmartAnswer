"""OpenAI 兼容聊天生图协议适配器。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .contracts import GeneratedImage, ImageGenerationProviderError, ImageGenerationRequest
from .openai_images import OpenAIImageGenerationProvider


IMAGE_DATA_URL_PATTERN = re.compile(
    r"data:(?P<mime>image/(?:png|jpe?g|webp));base64,(?P<data>[A-Za-z0-9+/=_\s-]+)",
    re.IGNORECASE,
)
IMAGE_MARKDOWN_URL_PATTERN = re.compile(r"!\[[^\]]*\]\((?P<url>https?://[^\s)]+)\)")


@dataclass(slots=True)
class OpenAIChatImageGenerationProvider(OpenAIImageGenerationProvider):
    """调用以聊天补全返回图片的 OpenAI 兼容生图服务。"""

    provider_name: str = "openai-chat-image"

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        """请求聊天生图，并读取 Markdown 或内容块中的首张图片。"""

        response = self._post_json(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "modalities": ["text", "image"],
                "stream": False,
            },
            endpoint="chat/completions",
        )
        item = image_item_from_chat_response(response)
        content, mime_type = self._read_image(item)
        return GeneratedImage(
            content=content,
            mime_type=mime_type,
            width=0,
            height=0,
            provider_request_id=str(response.get("id") or ""),
        )


def image_item_from_chat_response(response: dict[str, Any]) -> dict[str, str]:
    """从 OpenAI 兼容聊天响应中提取首个图片数据项。"""

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务返回了无效的聊天响应"
        ) from exc
    item = image_item_from_content(content)
    if item is None:
        raise ImageGenerationProviderError(
            "PROVIDER_INVALID_RESPONSE", "生图服务未在聊天响应中返回图片内容"
        )
    return item


def image_item_from_content(content: object) -> dict[str, str] | None:
    """识别兼容网关常见的 Markdown、data URL 与内容块图片形态。"""

    if isinstance(content, str):
        return image_item_from_text(content)
    if not isinstance(content, list):
        return None
    for part in content:
        if not isinstance(part, dict):
            continue
        image_url = part.get("image_url")
        if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
            return image_item_from_text(str(image_url["url"]))
        for key in ("url", "data_url", "b64_json"):
            value = part.get(key)
            if not isinstance(value, str):
                continue
            if key == "b64_json":
                return {"b64_json": value, "mime_type": str(part.get("mime_type") or "image/png")}
            item = image_item_from_text(value)
            if item is not None:
                return item
    return None


def image_item_from_text(value: str) -> dict[str, str] | None:
    """把 Markdown 图片或 data URL 归一为 Images 适配器可读取的字典。"""

    match = IMAGE_DATA_URL_PATTERN.search(value)
    if match:
        return {
            "b64_json": re.sub(r"\s+", "", match.group("data")),
            "mime_type": match.group("mime").lower(),
        }
    markdown_match = IMAGE_MARKDOWN_URL_PATTERN.search(value)
    if markdown_match:
        return {"url": markdown_match.group("url")}
    if value.startswith(("https://", "http://")):
        return {"url": value}
    return None
