"""答题链路中的缓存、图片和模型答案安全策略。"""

from __future__ import annotations

from ..input_anomalies import normalize_image_data_urls, normalize_image_urls
from ..media import is_ocs_image_url
from ..models import QuestionQuery


def is_image_context_without_text_snapshot(query: QuestionQuery) -> bool:
    """图片题没有 OCR 文本快照时，不把 URL 题干沉淀为可复用题。"""

    if not normalize_image_urls(query.image_urls, (query.title,)):
        return False
    return not str(query.title or "").strip() or bool(normalize_image_urls((query.title,)))


def has_unhydrated_image_context(query: QuestionQuery) -> bool:
    """图片题必须先转成本地图床 URL 或 data URL，避免把第三方外链交给模型下载。"""

    image_urls = normalize_image_urls(
        query.image_urls,
        (query.title,),
        query.option_image_urls.values(),
    )
    if not image_urls:
        return False
    if all(is_ocs_image_url(url) for url in image_urls):
        return False
    return not bool(
        normalize_image_data_urls(
            query.image_data_urls,
            query.option_image_data_urls.values(),
        )
    )
