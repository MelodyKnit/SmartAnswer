"""用户私有生图参考图和蒙版的校验、规范化与文件访问。"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..config import get_global_config
from .image_assets import (
    PrivateImageError,
    atomic_store_private_image,
    delete_private_image,
    safe_private_image_path,
    validate_private_image,
)


@dataclass(frozen=True, slots=True)
class StoredGenerationInputImage:
    """已落盘的参考图或规范化蒙版。"""

    storage_key: str
    content_hash: str
    mime_type: str
    width: int
    height: int
    byte_size: int


def store_generation_input_image(
    *,
    input_id: str,
    content: bytes,
    kind: str,
) -> StoredGenerationInputImage:
    """保存上传输入图；蒙版被转换为黑白 PNG 的统一语义。"""

    if kind == "mask":
        content = canonicalize_mask_image(content)
    image = validate_private_image(content, subject="上传图片")
    storage_key = f"{input_id}.{image.extension}"
    atomic_store_private_image(
        get_global_config().generation_input_images_dir,
        storage_key=storage_key,
        content=image.content,
    )
    return StoredGenerationInputImage(
        storage_key=storage_key,
        content_hash=image.content_hash,
        mime_type=image.mime_type,
        width=image.width,
        height=image.height,
        byte_size=image.byte_size,
    )


def canonicalize_mask_image(content: bytes) -> bytes:
    """将用户蒙版转换为 PNG，白色表示编辑区域、黑色表示保留区域。"""

    image = validate_private_image(content, subject="蒙版图片")
    try:
        with Image.open(io.BytesIO(image.content)) as source:
            rgba = source.convert("RGBA")
            # 有透明信息时优先按 Alpha 决定编辑区域；否则按亮度二值化。
            alpha = rgba.getchannel("A")
            alpha_extrema = alpha.getextrema()
            if alpha_extrema != (255, 255):
                binary = alpha.point(lambda value: 255 if value >= 128 else 0)
            else:
                binary = rgba.convert("L").point(lambda value: 255 if value >= 128 else 0)
            buffer = io.BytesIO()
            binary.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except OSError as exc:
        raise PrivateImageError("蒙版图片无法规范化") from exc


def generation_input_image_path(storage_key: str) -> Path | None:
    """在受控输入目录内解析图片路径。"""

    return safe_private_image_path(get_global_config().generation_input_images_dir, storage_key)


def delete_generation_input_image(storage_key: str) -> None:
    """删除上传输入图，保留调用方的数据库软删除语义。"""

    delete_private_image(get_global_config().generation_input_images_dir, storage_key)
