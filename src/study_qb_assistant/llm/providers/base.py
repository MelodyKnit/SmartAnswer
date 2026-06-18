"""基于模型的答案生成服务提供商接口契约。"""

from __future__ import annotations

from typing import Protocol

from ...models import ModelAnswer, QuestionQuery


class ModelProvider(Protocol):
    """模型答题提供者必须满足的最小接口。"""

    provider_name: str

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """根据题目查询生成模型答案。"""
