"""图片题不可读相关异常识别策略。"""

from __future__ import annotations

from .inputs import normalize_image_urls
from study_qb_assistant.questions.models import ModelAnswer, QuestionQuery


def model_answer_indicates_unreadable_image(query: QuestionQuery, answer: ModelAnswer) -> bool:
    """识别模型实际没有读到图片却返回了低置信度占位文本的情况。"""

    if not normalize_image_urls(query.image_urls, (query.title,)):
        return False
    combined = " ".join(
        value
        for value in (answer.candidate_answer, answer.answer_text, answer.explanation)
        if value
    ).casefold()
    unreadable_markers = (
        "can't access the image",
        "cannot access the image",
        "无法访问图片",
        "无法查看图片",
        "看不到图片",
        "不能确定正确选项",
    )
    return answer.confidence < 0.3 or any(marker in combined for marker in unreadable_markers)


def provider_error_indicates_unreadable_image(query: QuestionQuery, error: Exception) -> bool:
    """识别图片题在模型请求阶段就因图片不可读而失败的异常。"""

    if not normalize_image_urls(query.image_urls, (query.title,)):
        return False
    combined = str(error or "").casefold()
    unreadable_markers = (
        "can't access the image",
        "cannot access the image",
        "failed to download file",
        "error getting file type",
        "image unreadable",
        "无法访问图片",
        "无法查看图片",
        "看不到图片",
        "count_token_failed",
        "status code: 403",
    )
    return any(marker in combined for marker in unreadable_markers)
