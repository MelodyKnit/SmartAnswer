"""题目图片输入的识别、去重与文本清洗。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from study_qb_assistant.questions.models import QuestionQuery

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
DATA_URL_PATTERN = re.compile(r"^data:image/[-+.\w]+;base64,[A-Za-z0-9+/=\s]+$", re.I)
EMBEDDED_IMAGE_URL_PATTERN = re.compile(
    r"https?://[^\s\u3000\"'<>]+?\.(?:png|jpg|jpeg|webp|gif|bmp)(?:\?[^\s\u3000\"'<>]*)?",
    re.I,
)


def is_image_url(value: str) -> bool:
    """判断字符串是否像直接指向图片资源的 URL。"""

    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if "://" in parsed.path or "://" in parsed.netloc:
        return False
    return parsed.path.lower().endswith(IMAGE_EXTENSIONS)


def normalize_image_urls(*groups: object) -> tuple[str, ...]:
    """从多个输入来源提取去重后的图片 URL。"""

    urls: list[str] = []
    for group in groups:
        candidates: Iterable[object]
        if isinstance(group, str):
            candidates = (*re.split(r"[\s,，]+", group), *EMBEDDED_IMAGE_URL_PATTERN.findall(group))
        elif isinstance(group, Iterable):
            candidates = group
        else:
            candidates = ()
        for candidate in candidates:
            text = str(candidate or "").strip()
            for value in (text, *EMBEDDED_IMAGE_URL_PATTERN.findall(text)):
                if is_image_url(value) and value not in urls:
                    urls.append(value)
    return tuple(urls)


def is_image_data_url(value: str) -> bool:
    """判断字符串是否是图片 data URL。"""

    text = str(value or "").strip()
    return bool(text and DATA_URL_PATTERN.match(text))


def normalize_image_data_urls(*groups: object) -> tuple[str, ...]:
    """从多个输入来源提取去重后的图片 data URL。"""

    urls: list[str] = []
    for group in groups:
        candidates: Iterable[object]
        if isinstance(group, str):
            candidates = (group,)
        elif isinstance(group, Iterable):
            candidates = group
        else:
            candidates = ()
        for candidate in candidates:
            text = str(candidate or "").strip()
            if is_image_data_url(text) and text not in urls:
                urls.append(text)
    return tuple(urls)


def legacy_image_url_only(query: QuestionQuery) -> bool:
    """判断当前图片题是否仍停留在只传 URL 的旧链路。"""

    return bool(normalize_image_urls(query.image_urls, (query.title,))) and not bool(
        normalize_image_data_urls(query.image_data_urls, query.option_image_data_urls.values())
    )


def strip_embedded_image_urls(title: str, *groups: object) -> str:
    """移除题干中的裸露图片 URL，避免污染文本匹配与模型输入。"""

    raw = str(title or "").strip()
    if not raw:
        return ""
    image_urls = normalize_image_urls((raw,), *groups)
    cleaned = raw
    for url in image_urls:
        if cleaned != url:
            cleaned = cleaned.replace(url, " ")
    cleaned = EMBEDDED_IMAGE_URL_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", cleaned)
    cleaned = re.sub(r"([\u4e00-\u9fff])\s+(_{2,})", r"\1\2", cleaned)
    cleaned = re.sub(r"(_{2,})\s+([、，。,.])", r"\1\2", cleaned)
    if cleaned:
        return cleaned
    return "" if image_urls else raw
