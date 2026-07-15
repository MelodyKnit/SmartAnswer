"""OCS 题型处理策略基础契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from study_qb_assistant.questions.models import QueryResult


@dataclass(slots=True, frozen=True)
class OcsFormattedAnswer:
    """OCS 可消费的答案与诊断信息。"""

    answer: str | None
    shape: str
    diagnostics: dict[str, object] = field(default_factory=dict)

    def diagnostic_payload(self) -> dict[str, object]:
        """返回包含统一答案形态字段的诊断载荷。"""

        return {"ocs_answer_shape": self.shape, **self.diagnostics}


class BaseOcsQuestionTypeHandler(ABC):
    """OCS 题型答案格式化策略基类。"""

    canonical_type: str
    aliases: frozenset[str]

    def matches(self, raw_type: str, result: QueryResult) -> bool:
        """判断当前策略是否可处理请求题型。"""

        return raw_type.strip().casefold() in self.aliases

    @abstractmethod
    def format_answer(self, result: QueryResult) -> OcsFormattedAnswer:
        """把内部答案格式化为 OCS 可消费形态。"""
