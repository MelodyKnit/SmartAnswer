"""大模型配置与调用追溯仓储。"""

from __future__ import annotations

from ...llm.management.records import LlmCallTraceRecord, LlmModelRecord
from . import llm_queries
from .base import SqlAlchemyRepository
from .settings import SettingsRepository


class LlmRepository(SqlAlchemyRepository):
    """把现有 LLM 持久化函数收敛为领域仓储接口。"""

    def __init__(self, session_factory, settings: SettingsRepository) -> None:
        super().__init__(session_factory)
        self.settings = settings

    def get_settings(self, scope: str, *, keys: set[str] | None = None) -> dict[str, str]:
        return self.settings.get_settings(scope, keys=keys)

    def set_settings(self, scope: str, values: dict[str, str]) -> None:
        self.settings.set_settings(scope, values)

    def replace_settings(self, scope: str, values: dict[str, str]) -> None:
        self.settings.replace_settings(scope, values)

    def list_llm_models(self) -> list[LlmModelRecord]:
        return llm_queries.list_llm_models(self.session_factory)

    def get_llm_model(self, model_id: str) -> LlmModelRecord | None:
        return llm_queries.get_llm_model(self.session_factory, model_id)

    def save_llm_model(self, record: LlmModelRecord) -> LlmModelRecord:
        return llm_queries.save_llm_model(self.session_factory, record)

    def delete_llm_model(self, model_id: str) -> bool:
        return llm_queries.delete_llm_model(self.session_factory, model_id)

    def save_llm_call_trace(self, record: LlmCallTraceRecord) -> None:
        llm_queries.save_llm_call_trace(self.session_factory, record)

    def list_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[LlmCallTraceRecord]:
        return llm_queries.list_llm_call_traces(
            self.session_factory,
            request_id=request_id,
            model_id=model_id,
            phase=phase,
            limit=limit,
            offset=offset,
        )

    def count_llm_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
    ) -> int:
        return llm_queries.count_llm_call_traces(
            self.session_factory,
            request_id=request_id,
            model_id=model_id,
            phase=phase,
        )

    def llm_call_stats(self) -> list[dict]:
        return llm_queries.llm_call_stats(self.session_factory)
