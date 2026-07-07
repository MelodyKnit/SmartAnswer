"""图片题上下文兼容入口。

新代码请优先使用 :mod:`study_qb_assistant.media.question_context`。本模块保留
旧导入路径，避免一次性修改所有调用方。
"""

from __future__ import annotations

from .media.question_context import (
    CHAOXING_IMAGE_REFERER,
    DATA_URL_PREFIX_PATTERN,
    IMAGE_FETCH_ACCEPT,
    IMAGE_FETCH_USER_AGENT,
    MAX_IMAGE_BYTES,
    ImageAsset,
    browser_image_request_headers,
    build_model_query,
    build_ocr_query,
    decode_image_data_url,
    extract_title_from_ocr_text,
    fetch_image_via_playwright,
    fetch_public_image,
    fetch_public_image_asset,
    fetch_public_image_with_mime,
    guess_image_mime,
    image_bytes_to_data_url,
    image_request_referer,
    is_public_http_url,
    load_query_image_assets,
    log_image_hydration,
    ocr_image_bytes,
    parse_options_from_ocr_text,
)

__all__ = [
    "CHAOXING_IMAGE_REFERER",
    "DATA_URL_PREFIX_PATTERN",
    "IMAGE_FETCH_ACCEPT",
    "IMAGE_FETCH_USER_AGENT",
    "MAX_IMAGE_BYTES",
    "ImageAsset",
    "browser_image_request_headers",
    "build_model_query",
    "build_ocr_query",
    "decode_image_data_url",
    "extract_title_from_ocr_text",
    "fetch_image_via_playwright",
    "fetch_public_image",
    "fetch_public_image_asset",
    "fetch_public_image_with_mime",
    "guess_image_mime",
    "image_bytes_to_data_url",
    "image_request_referer",
    "is_public_http_url",
    "load_query_image_assets",
    "log_image_hydration",
    "ocr_image_bytes",
    "parse_options_from_ocr_text",
]
