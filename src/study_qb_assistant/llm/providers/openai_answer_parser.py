"""OpenAI 兼容模型答案解析与规范化工具。"""

from __future__ import annotations

import json
import re

from ...models import ModelAnswer, QuestionQuery
from ...option_labels import canonicalize_label_answer
from ...logger import log_event
from ...question_types import JUDGEMENT_TYPES, has_blank_marker


def strip_json_fence(content: str) -> str:
    """去除 Markdown 代码块围栏。"""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def optional_string(value: object) -> str | None:
    """把对象安全转换为去空白后的字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_float(value: object) -> float | None:
    """把对象安全转换为浮点数。"""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def answer_field(value: object) -> str | None:
    """解析 `candidate_answer` 字段。"""
    if isinstance(value, (list, tuple)):
        parts = [optional_string(item) for item in value]
        return "#".join(part for part in parts if part)
    return optional_string(value)


def text_field(value: object) -> str | None:
    """解析 `answer_text` 字段。"""
    if isinstance(value, (list, tuple)):
        parts = [optional_string(item) for item in value]
        return "；".join(part for part in parts if part)
    return optional_string(value)


def completion_answer_field(
    candidate_value: object,
    answer_text_value: object,
    *,
    blanks: int = 0,
) -> str | None:
    """把多空填空答案编码成 OCS 可拆分的 JSON 数组字符串。"""
    for value in (candidate_value, answer_text_value):
        if isinstance(value, (list, tuple)):
            parts = [optional_string(item) for item in value]
            normalized = [part for part in parts if part]
            if normalized:
                return json.dumps(normalized, ensure_ascii=False)
    for value in (candidate_value, answer_text_value):
        grouped_parts = grouped_completion_parts(value, blanks=blanks)
        if grouped_parts:
            return json.dumps(grouped_parts, ensure_ascii=False)
    answer = answer_field(candidate_value) or text_field(answer_text_value)
    if answer and blanks <= 1:
        return strip_single_blank_wrapper(answer)
    return answer


def parse_plain_text_answer(content: str) -> ModelAnswer:
    """尽力而为地从纯文本中提取模型答案。"""
    normalized = content.strip()
    choice_match = re.search(
        r"(?:答案|answer|选项)?\s*[:：是为]?\s*([A-F](?:[#、,，;；\s]*[A-F]){0,7})\b",
        normalized,
        re.IGNORECASE,
    )
    if choice_match:
        answer = choice_match.group(1).upper()
        return ModelAnswer(
            candidate_answer=answer,
            answer_text=answer,
            explanation=normalized,
            confidence=0.45,
        )
    if any(token in normalized for token in ("正确", "对", "true", "True", "TRUE")):
        return ModelAnswer("true", "正确", normalized, 0.4)
    if any(token in normalized for token in ("错误", "错", "false", "False", "FALSE")):
        return ModelAnswer("false", "错误", normalized, 0.4)
    return ModelAnswer(None, None, normalized or None, 0.0)


def normalize_answer_for_query(answer: ModelAnswer, query: QuestionQuery | None) -> ModelAnswer:
    """根据题型和选项，把模型答案规范化为系统内部可消费格式。"""
    if is_judgement_without_options(query):
        return normalize_judgement_without_options(answer)
    if is_completion_without_options(query):
        return answer
    if not query or not query.options:
        return answer

    normalized_candidate = candidate_to_labels(answer.candidate_answer or "", query)
    if not normalized_candidate:
        normalized_candidate = candidate_to_labels(answer.answer_text or "", query)
    if not normalized_candidate:
        return answer_without_fillable_content(answer)
    if normalized_candidate != answer.candidate_answer:
        log_event(
            "model_answer_normalized",
            {
                "title": query.title,
                "question_type": query.question_type,
                "original_candidate": answer.candidate_answer,
                "normalized_candidate": normalized_candidate,
            },
        )

    rebuilt_answer_text = answer_text_from_labels(normalized_candidate, query)
    answer_text = rebuilt_answer_text or answer.answer_text
    return ModelAnswer(
        candidate_answer=normalized_candidate,
        answer_text=answer_text,
        explanation=answer.explanation,
        confidence=answer.confidence,
        question_form=answer.question_form,
        reuse_policy=answer.reuse_policy,
        reuse_reason=answer.reuse_reason,
        reuse_confidence=answer.reuse_confidence,
    )


def candidate_to_labels(candidate_answer: str, query: QuestionQuery) -> str | None:
    """将候选答案标准化为 `A` 或 `A#B` 这类标签形式。"""
    compact = candidate_answer.strip().upper().replace(" ", "")
    if re.fullmatch(r"[A-F](?:#[A-F])*", compact):
        normalized = canonicalize_label_answer(query, compact)
        if normalized:
            return normalized
    if query.question_type.lower() in {"multiple", "multi", "多选", "多选题"} and re.fullmatch(
        r"[A-F]{2,}", compact
    ):
        normalized = canonicalize_label_answer(query, compact)
        if normalized:
            return normalized

    mapped: list[str] = []
    for part in split_candidate_parts(candidate_answer):
        label = part_to_label(part, query)
        if not label:
            return None
        mapped.append(label)
    if not mapped:
        return None
    return canonicalize_label_answer(query, "#".join(mapped))


def is_completion_without_options(query: QuestionQuery | None) -> bool:
    """判断当前查询是否为无选项填空题。"""
    if query is None or query.options:
        return False
    normalized_type = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or title.startswith("填空题")
        or has_blank_marker(title)
    )


def is_judgement_without_options(query: QuestionQuery | None) -> bool:
    """判断当前查询是否为无选项判断题。"""

    if query is None or query.options:
        return False
    normalized_type = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return normalized_type in JUDGEMENT_TYPES or title.startswith("判断题")


def normalize_judgement_without_options(answer: ModelAnswer) -> ModelAnswer:
    """把无选项判断题答案收敛为内部 A/B 标签。"""

    signal = judgement_signal(answer.candidate_answer) or judgement_signal(answer.answer_text)
    if signal is None:
        return answer
    label, text = signal
    return ModelAnswer(
        candidate_answer=label,
        answer_text=text,
        explanation=answer.explanation,
        confidence=answer.confidence,
        question_form=answer.question_form,
        reuse_policy=answer.reuse_policy,
        reuse_reason=answer.reuse_reason,
        reuse_confidence=answer.reuse_confidence,
        source_query=answer.source_query,
    )


def judgement_signal(value: str | None) -> tuple[str, str] | None:
    """识别判断题常见真假表述。"""

    normalized = str(value or "").strip().casefold()
    if normalized in {"a", "对", "正确", "true", "yes"}:
        return "A", "对"
    if normalized in {"b", "错", "错误", "false", "no"}:
        return "B", "错"
    return None


def answer_without_fillable_content(answer: ModelAnswer) -> ModelAnswer:
    """保留解释信息，但清空不符合题型契约的可填答案。"""

    return ModelAnswer(
        candidate_answer=None,
        answer_text=None,
        explanation=answer.explanation,
        confidence=min(answer.confidence, 0.2),
        question_form=answer.question_form,
        reuse_policy=answer.reuse_policy,
        reuse_reason=answer.reuse_reason,
        reuse_confidence=(
            min(answer.reuse_confidence, 0.2) if answer.reuse_confidence is not None else None
        ),
        source_query=answer.source_query,
    )


def grouped_completion_parts(value: object, *, blanks: int) -> list[str]:
    """从模型常见的括号/空格多空答案中提取每个空的答案。"""

    text = optional_string(value)
    if not text or blanks <= 1:
        return []
    bracketed = [
        part.strip()
        for groups in re.findall(r"\(([^()]*)\)|（([^（）]*)）", text)
        for part in groups
        if part.strip()
    ]
    if len(bracketed) == blanks:
        return bracketed
    words = [part.strip() for part in re.split(r"\s+", text) if part.strip()]
    if len(words) == blanks and all(len(word) <= 40 for word in words):
        return [strip_single_blank_wrapper(word) for word in words]
    return []


def strip_single_blank_wrapper(value: str) -> str:
    """去掉模型给单个填空答案额外包上的空位括号。"""

    text = value.strip()
    bracketed = re.fullmatch(r"\(([^()]*)\)|（([^（）]*)）", text)
    if not bracketed:
        return text
    return next(part.strip() for part in bracketed.groups() if part is not None)


def split_candidate_parts(candidate_answer: str) -> list[str]:
    """按常见分隔符拆分候选答案。"""
    return [part.strip() for part in re.split(r"[#;,，、；\n]+", candidate_answer) if part.strip()]


def part_to_label(part: str, query: QuestionQuery) -> str | None:
    """把单个答案片段映射回选项标签。"""
    labels = ("A", "B", "C", "D", "E", "F")
    compact = part.strip().upper()
    if re.fullmatch(r"[A-F]", compact) and labels.index(compact) < len(query.options):
        return compact

    normalized_part = normalize_option_text(part)
    for label, option in zip(labels, query.options, strict=False):
        if normalized_part == normalize_option_text(option):
            return label
    return None


def answer_text_from_labels(candidate_answer: str, query: QuestionQuery) -> str | None:
    """根据标签字符串反向拼接选项文本。"""
    labels = ("A", "B", "C", "D", "E", "F")
    option_map = {
        label: strip_option_label(option)
        for label, option in zip(labels, query.options, strict=False)
    }
    parts = [option_map.get(label) for label in candidate_answer.split("#")]
    texts = [part for part in parts if part]
    return "；".join(texts) if texts else None


def strip_option_label(option: str) -> str:
    """去除选项文本前缀中的字母标签。"""
    return re.sub(r"^\s*[A-Fa-f][\.、．:：]\s*", "", option).strip()


def normalize_option_text(option: str) -> str:
    """对选项文本做清洗后再比较。"""
    return re.sub(r"\s+", "", strip_option_label(option)).lower()


def decode_chat_response(response_body: str) -> dict:
    """解析聊天补全接口返回体。"""
    stripped = response_body.lstrip()
    if stripped.startswith("data:"):
        return decode_streaming_chat_response(response_body)
    return json.loads(response_body)


def decode_streaming_chat_response(response_body: str) -> dict:
    """解析 SSE 流式返回，并重组成标准响应结构。"""
    content_parts: list[str] = []
    for event_payload in iter_sse_payloads(response_body):
        if event_payload == "[DONE]":
            continue
        try:
            chunk = json.loads(event_payload)
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices") or ():
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                content_parts.append(str(content))
            message = choice.get("message") or {}
            message_content = message.get("content")
            if message_content:
                content_parts.append(str(message_content))

    content = "".join(content_parts).strip()
    if not content:
        raise RuntimeError("streaming model response contained no answer content")
    return {"choices": [{"message": {"content": content}}]}


def iter_sse_payloads(response_body: str) -> list[str]:
    """提取 SSE 响应中的 `data:` 负载。"""
    payloads: list[str] = []
    current: list[str] = []
    for raw_line in response_body.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                payloads.append("\n".join(current))
                current = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            current.append(line.removeprefix("data:").strip())
    if current:
        payloads.append("\n".join(current))
    return payloads


def bool_from_env(value: str | None, *, default: bool) -> bool:
    """解析布尔环境变量。"""
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def int_from_env(value: str | None, *, default: int) -> int:
    """解析正整数环境变量。"""
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
