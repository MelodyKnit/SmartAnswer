"""答题服务依赖的协议定义。"""

from __future__ import annotations

from typing import Protocol

from ..models import CanonicalQuestionRecord


class QuestionRecordRepository(Protocol):
    """AI 答题沉淀只依赖题库仓储的保存能力。"""

    def save_question_record(self, record: CanonicalQuestionRecord) -> None:
        """保存或更新题库记录。"""
        ...
