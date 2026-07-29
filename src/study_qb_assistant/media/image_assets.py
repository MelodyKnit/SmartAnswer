"""私有生图输入和输出资产共享的图片校验与安全落盘工具。"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


MAX_PRIVATE_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_PRIVATE_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
MAX_PRIVATE_IMAGE_PIXELS = 40_000_000


class PrivateImageError(ValueError):
    """私有图片内容无法安全保存或使用。"""


@dataclass(frozen=True, slots=True)
class ValidatedPrivateImage:
    """通过格式、尺寸和大小校验的图片信息。"""

    content: bytes
    content_hash: str
    mime_type: str
    extension: str
    width: int
    height: int
    byte_size: int


def validate_private_image(content: bytes, *, subject: str) -> ValidatedPrivateImage:
    """验证 PNG、JPEG 或 WEBP 图片，拒绝异常格式与过大像素图。"""

    if not content:
        raise PrivateImageError(f"{subject}未包含图片内容")
    if len(content) > MAX_PRIVATE_IMAGE_BYTES:
        raise PrivateImageError(f"{subject}超过 10MB 存储上限")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            format_name = str(image.format or "").upper()
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise PrivateImageError(f"{subject}不是有效图片") from exc
    if format_name not in ALLOWED_PRIVATE_IMAGE_FORMATS:
        raise PrivateImageError(f"{subject}仅支持 PNG、JPEG 或 WEBP 格式")
    if width < 1 or height < 1 or width * height > MAX_PRIVATE_IMAGE_PIXELS:
        raise PrivateImageError(f"{subject}尺寸不在允许范围内")
    mime_type, extension = ALLOWED_PRIVATE_IMAGE_FORMATS[format_name]
    return ValidatedPrivateImage(
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        mime_type=mime_type,
        extension=extension,
        width=width,
        height=height,
        byte_size=len(content),
    )


def atomic_store_private_image(
    directory: Path,
    *,
    storage_key: str,
    content: bytes,
) -> None:
    """原子写入经过调用方校验的私有图片，避免读到半写入文件。"""

    directory.mkdir(parents=True, exist_ok=True)
    destination = safe_private_image_path(directory, storage_key)
    if destination is None:
        raise PrivateImageError("图片存储键无效")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(destination)


def safe_private_image_path(directory: Path, storage_key: str) -> Path | None:
    """仅解析受控目录下的简单文件名，防止目录穿越。"""

    raw = str(storage_key or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return None
    resolved_directory = directory.resolve()
    candidate = (resolved_directory / raw).resolve()
    try:
        candidate.relative_to(resolved_directory)
    except ValueError:
        return None
    return candidate


def delete_private_image(directory: Path, storage_key: str) -> None:
    """删除私有文件；文件已不存在时保持幂等。"""

    path = safe_private_image_path(directory, storage_key)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
