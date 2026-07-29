"""私有生图资产的校验、落盘与清理。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import get_global_config
from .image_assets import (
    ALLOWED_PRIVATE_IMAGE_FORMATS,
    MAX_PRIVATE_IMAGE_BYTES,
    PrivateImageError,
    atomic_store_private_image,
    delete_private_image,
    safe_private_image_path,
    validate_private_image,
)

# 保留旧名称，避免现有模型适配器和测试的公开导入路径失效。
MAX_GENERATED_IMAGE_BYTES = MAX_PRIVATE_IMAGE_BYTES
ALLOWED_GENERATED_IMAGE_FORMATS = ALLOWED_PRIVATE_IMAGE_FORMATS


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

    try:
        image = validate_private_image(content, subject="生成服务返回的图片")
    except PrivateImageError as exc:
        raise GeneratedImageError(str(exc)) from exc
    extension = image.extension
    storage_key = f"{asset_id}.{extension}"
    image_dir = get_global_config().generated_images_dir
    atomic_store_private_image(image_dir, storage_key=storage_key, content=image.content)
    return StoredGeneratedImage(
        storage_key=storage_key,
        content_hash=image.content_hash,
        mime_type=image.mime_type,
        width=image.width,
        height=image.height,
        byte_size=image.byte_size,
    )


def generated_image_path(storage_key: str) -> Path | None:
    """在受控目录内解析生成图片的物理路径。"""

    return safe_private_image_path(get_global_config().generated_images_dir, storage_key)


def delete_generated_image(storage_key: str) -> None:
    """删除不再被任务引用的生成图片，不抛出文件已不存在错误。"""

    delete_private_image(get_global_config().generated_images_dir, storage_key)
