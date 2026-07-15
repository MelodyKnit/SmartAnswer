"""本地检索和可选模型提供商之上的答案决议编排。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from study_qb_assistant.answering.quality import direct_known_answer, is_cache_safe_answer
from study_qb_assistant.answering.reuse import NON_REUSABLE_STATUS, decide_answer_reuse
from study_qb_assistant.questions.validation import InputAnomaly, analyze_query_input
from ..llm.cache import CachedLlmAnswer, LlmAnswerCache
from ..llm.contracts.tools import AnswerRetrievalPort
from ..llm.providers import ModelProvider
from ..llm.tools.local_rag import LocalRagTool
from ..media.image_anomalies import (
    model_answer_indicates_unreadable_image,
    provider_error_indicates_unreadable_image,
)
from study_qb_assistant.questions.models import ModelAnswer, QueryResult, QuestionQuery
from ..search import LocalQuestionIndex
from .non_answer_policy import (
    model_answer_has_fillable_content,
    model_answer_indicates_no_reliable_answer,
    result_from_input_anomaly,
    result_from_no_reliable_model_answer,
)
from .persistence import persist_model_answer_record
from .policies import is_image_context_without_text_snapshot
from .protocols import QuestionRecordRepository
from .retry import retry_model_answer

if TYPE_CHECKING:
    from ..llm.management import LlmManagementService
    from ..platform.settings import SettingsService


class AnswerService:
    """答案决议服务类，串联本地题库、规则、AI 缓存和大模型 fallback。"""

    def __init__(
        self,
        index: LocalQuestionIndex,
        model_provider: ModelProvider | None = None,
        *,
        allow_model_fallback: bool = False,
        explain_local_matches: bool = False,
        allow_known_rules: bool = True,
        no_local_bank_mode: bool = False,
        llm_answer_cache: LlmAnswerCache | None = None,
        trusted_confidence_threshold: float = 0.95,
        answer_retry_times: int = 3,
        answer_retrieval_tool: AnswerRetrievalPort | None = None,
    ) -> None:
        """初始化答案决议服务。"""

        self.index = index
        self.answer_retrieval_tool = answer_retrieval_tool or LocalRagTool(index)
        self.model_provider = model_provider
        self.allow_model_fallback = allow_model_fallback
        self.explain_local_matches = explain_local_matches
        self.allow_known_rules = allow_known_rules
        self.no_local_bank_mode = no_local_bank_mode
        self.llm_answer_cache = llm_answer_cache
        self.trusted_confidence_threshold = min(max(trusted_confidence_threshold, 0.0), 1.0)
        self.answer_retry_times = max(0, min(int(answer_retry_times), 10))
        self.runtime_settings_service: SettingsService | None = None
        self.model_management_service: LlmManagementService | None = None
        self.question_repository: QuestionRecordRepository | None = None

    def query(self, query: QuestionQuery) -> QueryResult:
        """查询问题的答案，返回带来源标记的本地结果或明确标识的模型结果。"""

        local_result: QueryResult | None = None
        image_only_query = is_image_context_without_text_snapshot(query)
        if not self.no_local_bank_mode and not image_only_query:
            local_result = self.answer_retrieval_tool.query(query, allow_fuzzy=False)
            if local_result.ok:
                if self.explain_local_matches and self.model_provider and not local_result.explanation:
                    return self._add_model_explanation(local_result, query)
                return local_result
            if local_result.error_code != "NOT_FOUND":
                return local_result

        direct_answer = direct_known_answer(query) if self.allow_known_rules else None
        if direct_answer is not None:
            return self._result_from_direct_answer(query, direct_answer)

        input_anomaly = analyze_query_input(query)
        if input_anomaly is not None:
            return result_from_input_anomaly(query, input_anomaly)

        cached_answer = (
            self.llm_answer_cache.get_trusted(query)
            if self.llm_answer_cache and not self.no_local_bank_mode
            else None
        )
        if cached_answer is not None:
            return self._result_from_cached_answer(query, cached_answer)

        if not self.no_local_bank_mode and not image_only_query:
            local_result = self.answer_retrieval_tool.query(query)
            if local_result.ok:
                if self.explain_local_matches and self.model_provider and not local_result.explanation:
                    return self._add_model_explanation(local_result, query)
                return local_result

        if (
            self.allow_model_fallback
            and self.model_provider
            and (local_result is None or local_result.error_code == "NOT_FOUND")
        ):
            return self._model_fallback(query)

        if local_result is not None:
            return local_result
        return QueryResult(
            ok=False,
            query=query,
            candidate_answer=None,
            answer_text=None,
            explanation=None,
            confidence=0.0,
            resolution_mode="not_found",
            review_required=True,
            error_code="NOT_FOUND",
            error_message="no trusted local match found",
        )

    def status(self) -> dict:
        """获取非敏感的服务运行时配置与状态信息，用于服务验证。"""

        provider_name = self.model_provider.provider_name if self.model_provider else None
        model_status: dict[str, object] = {
            "configured": self.model_provider is not None,
            "provider": provider_name,
            "fallback_enabled": self.allow_model_fallback,
            "explain_local_matches": self.explain_local_matches,
            "answer_retry_times": self.answer_retry_times,
        }
        if self.model_provider is not None:
            model_name = getattr(self.model_provider, "model", None)
            stream = getattr(self.model_provider, "stream", None)
            max_completion_tokens = getattr(self.model_provider, "max_completion_tokens", None)
            if model_name is not None:
                model_status["model"] = str(model_name)
            if stream is not None:
                model_status["stream"] = bool(stream)
            if max_completion_tokens is not None:
                model_status["max_completion_tokens"] = int(max_completion_tokens)
            search_enabled = getattr(self.model_provider, "search_enabled", None)
            search_provider = getattr(self.model_provider, "search_provider_name", None)
            if search_enabled is not None:
                model_status["search_enabled"] = bool(search_enabled)
            if search_provider is not None:
                model_status["search_provider"] = str(search_provider)
        cache_status = (
            self.llm_answer_cache.status()
            if self.llm_answer_cache is not None
            else {"enabled": False}
        )
        return {
            "lookup": self.index.status(),
            "model": model_status,
            "llm_answer_cache": cache_status,
        }

    def _add_model_explanation(self, result: QueryResult, query: QuestionQuery) -> QueryResult:
        """调用大模型为本地检索到的题目补全解析说明。"""

        assert self.model_provider is not None
        try:
            model_answer = self.model_provider.answer(query)
        except Exception:
            return result
        if model_answer.explanation:
            result.explanation = model_answer.explanation
            result.debug["provider"] = "local-normalized-jsonl+model-explanation"
        return result

    def _model_fallback(self, query: QuestionQuery) -> QueryResult:
        """本地未命中的情况下降级请求大模型获取答案，并记录缓存。"""

        assert self.model_provider is not None
        direct_answer = direct_known_answer(query) if self.allow_known_rules else None
        if direct_answer is not None:
            return self._result_from_direct_answer(query, direct_answer)

        cached_answer = (
            self.llm_answer_cache.get_trusted(query)
            if self.llm_answer_cache and not self.no_local_bank_mode
            else None
        )
        if cached_answer is not None:
            return self._result_from_cached_answer(query, cached_answer)

        attempts = 0
        try:
            model_answer, attempts = self._retry_model_answer(query)
        except Exception as exc:
            if provider_error_indicates_unreadable_image(query, exc):
                return result_from_input_anomaly(
                    query,
                    InputAnomaly(
                        code="IMAGE_UNREADABLE",
                        message="图片题无法可靠识别，未返回可填答案",
                        flags=("unreadable_image",),
                        context={
                            "provider": self.model_provider.provider_name,
                            "reason": str(exc),
                        },
                    ),
                )
            return QueryResult(
                ok=False,
                query=query,
                candidate_answer=None,
                answer_text=None,
                explanation=None,
                confidence=0.0,
                resolution_mode="model_error",
                review_required=True,
                error_code="MODEL_ERROR",
                error_message=str(exc),
                debug={
                    "provider": self.model_provider.provider_name,
                    "retry_attempts": str(attempts or (self.answer_retry_times + 1)),
                },
            )

        if model_answer_indicates_unreadable_image(query, model_answer):
            return result_from_input_anomaly(
                query,
                InputAnomaly(
                    code="IMAGE_UNREADABLE",
                    message="图片题无法可靠识别，未返回可填答案",
                    flags=("unreadable_image",),
                    context={"provider": self.model_provider.provider_name},
                ),
            )
        if (
            not model_answer_has_fillable_content(model_answer)
            or model_answer_indicates_no_reliable_answer(query, model_answer)
        ):
            return result_from_no_reliable_model_answer(
                query,
                model_answer,
                provider_name=self.model_provider.provider_name,
            )

        answer_query = model_answer.source_query or query
        confidence = max(0.0, min(model_answer.confidence, 1.0))
        cache_entry = None
        cache_status = "disabled"
        reuse_decision = decide_answer_reuse(
            answer_query,
            answer_text=model_answer.answer_text,
            candidate_answer=model_answer.candidate_answer,
            reuse_policy=model_answer.reuse_policy,
            question_form=model_answer.question_form,
            reuse_reason=model_answer.reuse_reason,
            reuse_confidence=model_answer.reuse_confidence,
        )
        image_context_without_text = is_image_context_without_text_snapshot(answer_query)
        safe_for_question_bank = reuse_decision.reusable and is_cache_safe_answer(
            answer_query, model_answer
        )
        if image_context_without_text:
            safe_for_question_bank = False
        has_answer_content = bool(
            str(model_answer.candidate_answer or "").strip()
            or str(model_answer.answer_text or "").strip()
        )
        if image_context_without_text:
            has_answer_content = False
        learned_status = reuse_decision.status if not reuse_decision.reusable else (
            "trusted"
            if safe_for_question_bank and confidence >= self.trusted_confidence_threshold
            else "low_confidence"
        )
        learned_record = None
        if has_answer_content:
            learned_record = self._persist_model_answer_record(
                answer_query,
                model_answer,
                status=learned_status,
                reuse_policy=reuse_decision.policy,
                reuse_tags=reuse_decision.tags,
                original_query=query,
            )
            if safe_for_question_bank and learned_record is not None and learned_status == "trusted":
                self.index.add_or_replace(learned_record)
        if self.llm_answer_cache is not None and safe_for_question_bank:
            cache_entry = self.llm_answer_cache.record_model_answer(
                answer_query,
                model_answer,
                provider_name=self.model_provider.provider_name,
                force_trusted=learned_status == "trusted" and self.question_repository is not None,
            )
            cache_status = cache_entry.status if cache_entry else "not_cached"
            if cache_entry is not None and cache_entry.status == "trusted":
                self.index.add_or_replace(cache_entry.to_record())
        elif self.llm_answer_cache is not None:
            cache_status = (
                "non_reusable_not_cached"
                if learned_status == NON_REUSABLE_STATUS
                else "image_context_not_cached"
                if image_context_without_text
                else "unsafe_not_cached"
            )
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer=model_answer.candidate_answer,
            answer_text=model_answer.answer_text,
            explanation=model_answer.explanation,
            confidence=confidence,
            resolution_mode="llm_fallback",
            review_required=True,
            sources=(
                {
                    "source_name": self.model_provider.provider_name,
                    "source_type": "model_provider",
                    "source_id": None,
                    "source_url": None,
                    "source_license": None,
                    "score": confidence,
                },
            ),
            debug={
                "provider": self.model_provider.provider_name,
                "llm_cache_status": cache_status,
                "question_bank_status": learned_status if has_answer_content else "no_answer",
                "reuse_policy": reuse_decision.policy,
                "image_context_not_cached": str(image_context_without_text).lower(),
                "answer_source_title": answer_query.title,
                "retry_attempts": str(attempts),
            },
        )

    def _retry_model_answer(self, query: QuestionQuery) -> tuple[ModelAnswer, int]:
        """在 AI/联网增强答题链路异常时按配置次数重试。"""

        return retry_model_answer(self, query)

    def _result_from_direct_answer(
        self,
        query: QuestionQuery,
        direct_answer: ModelAnswer,
    ) -> QueryResult:
        """从匹配到的高信号固定规则中封装标准 QueryResult。"""

        confidence = max(0.0, min(direct_answer.confidence, 1.0))
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer=direct_answer.candidate_answer,
            answer_text=direct_answer.answer_text,
            explanation=direct_answer.explanation,
            confidence=confidence,
            resolution_mode="known_rule",
            review_required=False,
            sources=(
                {
                    "source_name": "local-answer-quality-rules",
                    "source_type": "local_rule",
                    "source_id": None,
                    "source_url": None,
                    "source_license": None,
                    "score": confidence,
                },
            ),
            debug={"provider": "local-answer-quality-rules"},
        )

    def _result_from_cached_answer(
        self,
        query: QuestionQuery,
        cached_answer: CachedLlmAnswer,
    ) -> QueryResult:
        """从受信任的 LLM 自动沉淀题库条目中封装标准 QueryResult。"""

        confidence = max(0.0, min(cached_answer.confidence, 1.0))
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer=cached_answer.candidate_answer,
            answer_text=cached_answer.answer_text,
            explanation=cached_answer.explanation,
            confidence=confidence,
            resolution_mode="ai_cache",
            review_required=False,
            sources=(
                {
                    "source_name": "AIGenerated",
                    "source_type": "ai_generated_question_bank",
                    "source_id": cached_answer.to_record().question_id,
                    "source_url": None,
                    "source_license": "user-local-ai-generated",
                    "score": confidence,
                },
            ),
            debug={
                "provider": cached_answer.provider_name,
                "llm_cache_status": cached_answer.status,
                "ai_cache_confirmations": str(cached_answer.confirmations),
            },
        )

    def _persist_model_answer_record(
        self,
        query: QuestionQuery,
        answer: ModelAnswer,
        *,
        status: str,
        reuse_policy: str = "reusable",
        reuse_tags: tuple[str, ...] = (),
        original_query: QuestionQuery | None = None,
    ):
        """把结构化 AI 答案写入题库仓储，并按状态决定后续是否可命中。"""

        return persist_model_answer_record(
            self,
            query,
            answer,
            status=status,
            reuse_policy=reuse_policy,
            reuse_tags=reuse_tags,
            original_query=original_query,
        )
