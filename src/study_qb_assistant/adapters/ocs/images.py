"""OCS 编号图片输入校验与去重编号重映射。"""

from __future__ import annotations

import re
from typing import Any

from ...media.inputs import NUMBERED_IMAGE_PATTERN
from ...media.question_context import decode_image_data_url
from ...questions.parsing import QueryInputError
from ...questions.models import QuestionQuery

MAX_NUMBERED_IMAGES = 6
UNCONVERTED_IMAGE_PATTERN = re.compile(
    r"https?://[^\s\u3000\"'<>]+?\.(?:png|jpe?g|webp|gif|bmp|svg)(?=[?\s\u3000\u4e00-\u9fff]|$)",
    re.I,
)


def normalize_ocs_image_payload(payload: dict[str, Any]) -> tuple[int, ...]:
    """在通用解析器去重前，将文本图片编号映射到有效的唯一图片数组。

    OCS 的编号按原始 URL 分配；不同 URL 可能包含相同图片字节。文本编号
    必须与后续模型去重后的数组同步，转换失败的图片也不能静默移除。
    """

    title = str(payload.get("title") or "")
    raw_options = payload.get("options") or ()
    options = (raw_options,) if isinstance(raw_options, str) else tuple(raw_options)
    texts = (title, *(str(option) for option in options))
    if not any(NUMBERED_IMAGE_PATTERN.search(text) for text in texts):
        return ()

    raw_images = payload.get("image_data_urls") or ()
    unique_images: list[str] = []
    content_numbers: dict[tuple[str, bytes], int] = {}
    image_numbers: dict[int, int] = {}
    original_numbers: list[int] = []
    for old_number, raw_image in enumerate(raw_images, start=1):
        image = str(raw_image or "").strip()
        asset = decode_image_data_url(image)
        if asset is None or asset.mime_type not in {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "image/gif",
            "image/bmp",
        }:
            raise QueryInputError("图片数据无效或超过大小限制，请重新获取图片")
        # 按实际字节去重，避免 Base64 的空白或编码差异在图床中二次合并导致编号错位。
        content_key = (asset.mime_type.replace("image/jpg", "image/jpeg"), asset.content_bytes)
        if content_key not in content_numbers:
            unique_images.append(image)
            content_numbers[content_key] = len(unique_images)
            original_numbers.append(old_number)
        image_numbers[old_number] = content_numbers[content_key]
    if len(unique_images) > MAX_NUMBERED_IMAGES:
        raise QueryInputError("单次图片题最多支持 6 张不同图片")
    if any(UNCONVERTED_IMAGE_PATTERN.search(text) for text in texts):
        raise QueryInputError("题目图片未完整转换，请重新获取图片")

    def replace_number(match) -> str:
        number = image_numbers.get(int(match.group(1)))
        if number is None:
            raise QueryInputError("图片编号缺少对应的图片数据，请重新获取图片")
        return f"[图片{number}]"

    payload["title"] = NUMBERED_IMAGE_PATTERN.sub(replace_number, title)
    remapped_options = [NUMBERED_IMAGE_PATTERN.sub(replace_number, str(item)) for item in options]
    payload["options"] = remapped_options[0] if isinstance(raw_options, str) else remapped_options
    payload["image_data_urls"] = unique_images
    return tuple(original_numbers)


def restore_ocs_image_numbers(value: str | None, query: QuestionQuery) -> str | None:
    """将模型内部图片编号还原为客户端原编号，兼容 OCS 的 URL 还原逻辑。"""

    if not value or not query.ocs_image_numbers:
        return value

    def original_number(match) -> str:
        number = int(match.group(1))
        if not 1 <= number <= len(query.ocs_image_numbers):
            return match.group(0)
        return f"[图片{query.ocs_image_numbers[number - 1]}]"

    return NUMBERED_IMAGE_PATTERN.sub(original_number, value)
