"""模型提供者契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from study_qb_assistant.questions.models import ModelAnswer, QuestionQuery


@runtime_checkable
class ModelProvider(Protocol):
    """模型答题提供者必须满足的最小接口。"""

    provider_name: str

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """根据题目查询生成模型答案。"""


class BaseModelProvider(ABC):
    """项目内部模型实现的生命周期基础类。"""

    provider_name = "model-provider"

    @abstractmethod
    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """根据题目查询生成模型答案。"""

    def status(self) -> dict[str, object]:
        """返回提供者的最小运行状态。"""

        return {"provider": self.provider_name, "enabled": True}
