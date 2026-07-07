"""答题决议服务包。

本包保留 ``study_qb_assistant.answering`` 旧导入路径，同时把答题编排、重试、
沉淀和策略判断拆分到更明确的模块中。
"""

from __future__ import annotations

from ..media.question_context import build_model_query
from .protocols import QuestionRecordRepository
from .service import AnswerService

__all__ = ["AnswerService", "QuestionRecordRepository", "build_model_query"]
