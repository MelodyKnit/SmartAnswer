"""私有生图资产的校验、落盘与清理。"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..config import get_global_config

MAX_GENERATED_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_GENERATED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class GeneratedImageError(ValueError):
    """生成图片不符合安全存储约束。"""


@dataclass(frozen=True, slots=True)
class StoredGeneratedImage:
    """已校验并保存的私有图片资产。"""

    storage_key: str
    content_hash: str
    mime_type: str
    width: int
    height: int
    byte_size: int


def store_generated_image(*, asset_id: str, content: bytes) -> StoredGeneratedImage:
    """校验图片内容并原子写入运行数据目录。"""

    if not content:
        raise GeneratedImageError("生成服务未返回图片内容")
    if len(content) > MAX_GENERATED_IMAGE_BYTES:
        raise GeneratedImageError("生成图片超过 10MB 存储上限")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            format_name = str(image.format or "").upper()
            dimensions = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise GeneratedImageError("生成服务返回的内容不是有效图片") from exc
    if format_name not in ALLOWED_GENERATED_IMAGE_FORMATS:
        raise GeneratedImageError("仅支持 PNG、JPEG 或 WEBP 格式的生成图片")
    width, height = dimensions
    if width < 1 or height < 1 or width * height > 40_000_000:
        raise GeneratedImageError("生成图片尺寸不在允许范围内")
    mime_type, extension = ALLOWED_GENERATED_IMAGE_FORMATS[format_name]
    storage_key = f"{asset_id}.{extension}"
    image_dir = get_global_config().generated_images_dir
    image_dir.mkdir(parents=True, exist_ok=True)
    destination = image_dir / storage_key
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(destination)
    return StoredGeneratedImage(
        storage_key=storage_key,
        content_hash=hashlib.sha256(content).hexdigest(),
        mime_type=mime_type,
        width=width,
        height=height,
        byte_size=len(content),
    )


def generated_image_path(storage_key: str) -> Path | None:
    """在受控目录内解析生成图片的物理路径。"""

    raw = str(storage_key or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return None
    image_dir = get_global_config().generated_images_dir.resolve()
    candidate = (image_dir / raw).resolve()
    try:
        candidate.relative_to(image_dir)
    except ValueError:
        return None
    return candidate


def delete_generated_image(storage_key: str) -> None:
    """删除不再被任务引用的生成图片，不抛出文件已不存在错误。"""

    path = generated_image_path(storage_key)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
