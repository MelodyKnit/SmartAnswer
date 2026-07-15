"""本地题库检索的辅助函数。"""

from __future__ import annotations

import json
from pathlib import Path

from study_qb_assistant.questions.models import CanonicalQuestionRecord, QuestionQuery
from study_qb_assistant.questions.normalization import normalize_options


def read_jsonl_records(path: Path) -> list[CanonicalQuestionRecord]:
    """读取标准化 JSONL 题库记录。"""
    records: list[CanonicalQuestionRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(CanonicalQuestionRecord.from_dict(json.loads(line)))
    return records


def float_from_metadata(value: object, default: float) -> float:
    """安全解析元数据中的浮点数值。"""
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def is_ai_record(record: CanonicalQuestionRecord) -> bool:
    """判断题库记录是否属于 LLM 自动沉淀来源。"""
    return record.source_name == "AIGenerated" or "ai_generated" in record.tags


def record_options_match(record: CanonicalQuestionRecord, query: QuestionQuery) -> bool:
    """判断 LLM 自动沉淀题是否与当前查询选项完全一致。"""
    if not record.options_raw and not query.options:
        return True
    return normalize_options(record.options_raw) == normalize_options(query.options)
