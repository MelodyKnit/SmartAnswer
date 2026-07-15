"""Helpers for canonicalizing option-label answers across the project."""

from __future__ import annotations

import re

from study_qb_assistant.questions.models import QuestionQuery

LABELS = ("A", "B", "C", "D", "E", "F")
_MULTIPLE_TYPES = {"multiple", "multi", "多选", "多选题"}


def canonicalize_label_answer(query: QuestionQuery, value: str | None) -> str | None:
    """Normalize a label-based answer into a stable OCS-friendly form.

    Labels are deduplicated and ordered by the page option order. Non-multiple
    questions reject multi-label answers to avoid broadening matching semantics.
    """
    if not query.options or not value:
        return None
    selected = [label.upper() for label in re.findall(r"[A-F]", str(value))]
    valid_labels = set(LABELS[: len(query.options)])
    if not selected or any(label not in valid_labels for label in selected):
        return None

    ordered = [label for label in LABELS[: len(query.options)] if label in selected]
    if not ordered:
        return None

    question_type = (query.question_type or "").strip().lower()
    if question_type not in _MULTIPLE_TYPES and len(ordered) != 1:
        return None
    return "#".join(ordered)
