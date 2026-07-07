"""模型未给出可靠可填写答案时的判定与结果映射。"""

from __future__ import annotations

import re

from ..input_anomalies import InputAnomaly, result_from_input_anomaly
from ..models import ModelAnswer, QueryResult, QuestionQuery


def model_answer_indicates_no_reliable_answer(
    query: QuestionQuery, answer: ModelAnswer
) -> bool:
    """识别模型把“无法确定/信息不足”这类非答案错误写入答案字段的情况。

    这里判断的是通用不可作答语义，而不是某一道题的答案内容。若选择题已经规范化
    为合法选项标签，则优先信任标签，避免解析说明里的保守措辞误伤正常答案。
    """

    candidate = str(answer.candidate_answer or "").strip()
    if query.options and re.fullmatch(r"[A-F](?:#[A-F])*", candidate.upper()):
        return False

    primary_text = " ".join(
        value for value in (answer.candidate_answer, answer.answer_text) if value
    )
    if not primary_text.strip():
        return False
    combined = compact_for_non_answer_detection(
        " ".join(
            value
            for value in (answer.candidate_answer, answer.answer_text, answer.explanation)
            if value
        )
    )
    non_answer_markers = (
        "题目信息不足",
        "题目信息不完整",
        "题干信息不足",
        "题干信息不完整",
        "信息不足",
        "条件不足",
        "缺少必要条件",
        "缺少题干",
        "缺少选项",
        "无法确定",
        "不能确定",
        "无法判断",
        "无法作答",
        "无法可靠作答",
        "无法给出答案",
        "不能可靠作答",
        "不能给出答案",
        "看不清",
        "无法识别",
        "insufficientinformation",
        "notenoughinformation",
        "cannotdetermine",
        "can'tdetermine",
        "unabletoanswer",
        "cannotanswer",
    )
    return any(marker in combined for marker in non_answer_markers)


def model_answer_has_fillable_content(answer: ModelAnswer) -> bool:
    """判断模型答案是否包含可回填到题目的候选内容。"""

    return bool(
        str(answer.candidate_answer or "").strip()
        or str(answer.answer_text or "").strip()
    )


def result_from_no_reliable_model_answer(
    query: QuestionQuery, answer: ModelAnswer, *, provider_name: str
) -> QueryResult:
    """把模型未给出可靠答案的情况统一映射为不可回填结果。"""

    return result_from_input_anomaly(
        query,
        InputAnomaly(
            code="NO_RELIABLE_ANSWER",
            message="模型未返回可安全填写的答案",
            flags=("no_reliable_answer",),
            context={
                "provider": provider_name,
                "model_confidence": answer.confidence,
            },
        ),
    )


def compact_for_non_answer_detection(value: str) -> str:
    """压缩文本，便于识别模型返回的不可作答短语。"""

    return re.sub(r"\s+", "", str(value or "").casefold())
