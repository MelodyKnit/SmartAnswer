"""题目图片资产存储与本地图床 URL 生成。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from ..config import get_global_config
from ..logger import log_event
from ..models import QuestionQuery
from .question_context import ImageAsset, image_bytes_to_data_url, load_query_image_assets

IMAGE_ROUTE_PREFIX = "/media/ocs/images/"
IMAGE_FILENAME_PATTERN = re.compile(
    r"^[a-f0-9]{64}\.(?:png|jpg|jpeg|webp|gif|bmp)$",
    re.I,
)
MIME_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
}


@dataclass(slots=True)
class StoredQuestionImage:
    """描述已持久化到本地图床目录的题目图片。"""

    source_url: str
    mime_type: str
    sha256: str
    filename: str
    path: Path
    public_url: str
    data_url: str


def hydrate_query_images_for_model(query: QuestionQuery) -> QuestionQuery:
    """把题目图片保存为本地资产，并生成模型可访问的图片引用。"""

    assets = load_query_image_assets(query)
    if not assets:
        return query
    stored_images = tuple(
        stored for asset in assets if (stored := store_question_image(asset, query=query)) is not None
    )
    if not stored_images:
        return query
    public_urls = tuple(image.public_url for image in stored_images if image.public_url)
    if public_urls:
        log_model_image_refs(query, stored_images, mode="public_url")
        return QuestionQuery(
            title=query.title,
            options=query.options,
            question_type=query.question_type,
            request_id=query.request_id,
            page_url=query.page_url,
            image_capture_status=query.image_capture_status,
            image_capture_failures=query.image_capture_failures,
            image_urls=public_urls,
            image_data_urls=(),
            option_image_urls={},
            option_image_data_urls={},
            service_base_url=query.service_base_url,
        )
    data_urls = tuple(image.data_url for image in stored_images if image.data_url)
    if data_urls:
        log_model_image_refs(query, stored_images, mode="data_url_fallback")
        return QuestionQuery(
            title=query.title,
            options=query.options,
            question_type=query.question_type,
            request_id=query.request_id,
            page_url=query.page_url,
            image_capture_status=query.image_capture_status,
            image_capture_failures=query.image_capture_failures,
            image_urls=query.image_urls,
            image_data_urls=data_urls,
            option_image_urls=dict(query.option_image_urls),
            option_image_data_urls={},
            service_base_url=query.service_base_url,
        )
    return query


def store_question_image(asset: ImageAsset, *, query: QuestionQuery) -> StoredQuestionImage | None:
    """按图片内容哈希保存题目图片。"""

    extension = MIME_EXTENSIONS.get(asset.mime_type.lower())
    if not extension:
        log_event(
            "question_image_store",
            {
                "request_id": query.request_id,
                "ok": False,
                "reason": "unsupported_mime_type",
                "mime_type": asset.mime_type,
            },
        )
        return None
    digest = hashlib.sha256(asset.content_bytes).hexdigest()
    filename = f"{digest}.{extension}"
    image_dir = get_global_config().ocs_images_dir
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / filename
    if not path.exists():
        path.write_bytes(asset.content_bytes)
    public_url = public_image_url(filename, query=query)
    data_url = asset.data_url or image_bytes_to_data_url(asset.content_bytes, asset.mime_type)
    log_event(
        "question_image_store",
        {
            "request_id": query.request_id,
            "ok": True,
            "sha256": digest,
            "filename": filename,
            "mime_type": asset.mime_type,
            "byte_count": len(asset.content_bytes),
            "public_url_enabled": bool(public_url),
        },
    )
    return StoredQuestionImage(
        source_url=asset.source_url,
        mime_type=asset.mime_type,
        sha256=digest,
        filename=filename,
        path=path,
        public_url=public_url,
        data_url=data_url,
    )


def public_image_url(filename: str, *, query: QuestionQuery | None = None) -> str:
    """生成题目图片对外访问 URL。"""

    base_url = ""
    if query is not None and query.service_base_url:
        base_url = query.service_base_url
    if not base_url:
        base_url = get_global_config().public_base_url
    if not base_url:
        return ""
    return urljoin(base_url.rstrip("/") + "/", f"media/ocs/images/{filename}")


def is_safe_ocs_image_filename(filename: str) -> bool:
    """判断文件名是否是受控的图片资产名称。"""

    return bool(IMAGE_FILENAME_PATTERN.fullmatch(str(filename or "").strip()))


def is_ocs_image_url(url: str) -> bool:
    """判断 URL 是否指向本服务 OCS 图片图床路径。"""

    parsed = urlparse(str(url or "").strip())
    filename = Path(parsed.path).name
    return parsed.path.startswith(IMAGE_ROUTE_PREFIX) and is_safe_ocs_image_filename(filename)


def ocs_image_path(filename: str) -> Path | None:
    """根据安全文件名解析本地图片路径。"""

    if not is_safe_ocs_image_filename(filename):
        return None
    image_dir = get_global_config().ocs_images_dir.resolve()
    candidate = (image_dir / filename).resolve()
    try:
        candidate.relative_to(image_dir)
    except ValueError:
        return None
    return candidate


def log_model_image_refs(
    query: QuestionQuery,
    images: tuple[StoredQuestionImage, ...],
    *,
    mode: str,
) -> None:
    """记录模型实际使用的图片引用类型，不写入图片内容。"""

    log_event(
        "model_image_refs",
        {
            "request_id": query.request_id,
            "mode": mode,
            "image_count": len(images),
            "filenames": [image.filename for image in images[:6]],
        },
    )
