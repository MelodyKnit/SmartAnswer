"""大模型配置服务依赖的仓储契约。"""

from __future__ import annotations

from typing import Protocol

from ..management.records import LlmModelRecord


class LlmConfigRepository(Protocol):
    """声明模型配置与运行时设置所需的最小仓储能力。"""

    def list_llm_models(self) -> list[LlmModelRecord]: ...

    def get_llm_model(self, model_id: str) -> LlmModelRecord | None: ...

    def save_llm_model(self, record: LlmModelRecord) -> LlmModelRecord: ...

    def delete_llm_model(self, model_id: str) -> bool: ...

    def get_settings(
        self, scope: str, *, keys: set[str] | None = None
    ) -> dict[str, str]: ...

    def set_settings(self, scope: str, values: dict[str, str]) -> None: ...

    def replace_settings(self, scope: str, values: dict[str, str]) -> None: ...
