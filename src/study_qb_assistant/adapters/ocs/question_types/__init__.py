"""OCS 内置题型处理策略。"""

from .base import BaseOcsQuestionTypeHandler, OcsFormattedAnswer
from .completion import CompletionOcsHandler
from .judgement import JudgementOcsHandler
from .multiple import MultipleChoiceOcsHandler
from .single import SingleChoiceOcsHandler
from .unsupported import UnsupportedOcsQuestionTypeHandler

__all__ = [
    "BaseOcsQuestionTypeHandler",
    "CompletionOcsHandler",
    "JudgementOcsHandler",
    "MultipleChoiceOcsHandler",
    "OcsFormattedAnswer",
    "SingleChoiceOcsHandler",
    "UnsupportedOcsQuestionTypeHandler",
]
