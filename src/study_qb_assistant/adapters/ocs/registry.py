"""OCS 题型策略注册表。"""

from __future__ import annotations

from collections.abc import Iterable

from study_qb_assistant.questions.models import QueryResult
from .question_types import (
    BaseOcsQuestionTypeHandler,
    CompletionOcsHandler,
    JudgementOcsHandler,
    MultipleChoiceOcsHandler,
    SingleChoiceOcsHandler,
    UnsupportedOcsQuestionTypeHandler,
)


class OcsQuestionTypeRegistry:
    """注册并解析 OCS 题型处理策略。"""

    def __init__(
        self,
        handlers: Iterable[BaseOcsQuestionTypeHandler] = (),
        *,
        fallback: BaseOcsQuestionTypeHandler | None = None,
    ) -> None:
        self.handlers: list[BaseOcsQuestionTypeHandler] = []
        self.aliases: dict[str, BaseOcsQuestionTypeHandler] = {}
        self.fallback = fallback or UnsupportedOcsQuestionTypeHandler()
        for handler in handlers:
            self.register(handler)

    def register(self, handler: BaseOcsQuestionTypeHandler) -> None:
        """注册题型策略，重复别名会直接拒绝。"""

        normalized_aliases = {alias.strip().casefold() for alias in handler.aliases if alias.strip()}
        duplicates = sorted(alias for alias in normalized_aliases if alias in self.aliases)
        if duplicates:
            raise ValueError(f"OCS 题型别名重复: {', '.join(duplicates)}")
        self.handlers.append(handler)
        for alias in normalized_aliases:
            self.aliases[alias] = handler

    def resolve(self, raw_type: str, result: QueryResult) -> BaseOcsQuestionTypeHandler:
        """按显式别名优先、未知题型推断次之的顺序解析策略。"""

        normalized = (raw_type or "").strip().casefold()
        direct = self.aliases.get(normalized)
        if direct is not None:
            return direct

        # reader、line 等平台私有类型不能伪装成官方题型。
        if normalized not in {"", "unknown", "undefined"}:
            return self.fallback
        for handler in self.handlers:
            if handler.matches(normalized, result):
                return handler
        return self.fallback

    @classmethod
    def with_defaults(cls) -> "OcsQuestionTypeRegistry":
        """构建包含官方四类题型策略的默认注册表。"""

        return cls(
            (
                JudgementOcsHandler(),
                CompletionOcsHandler(),
                MultipleChoiceOcsHandler(),
                SingleChoiceOcsHandler(),
            )
        )
