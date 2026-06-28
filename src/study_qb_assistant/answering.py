"""本地检索和可选模型提供商之上的答案决议编排。

该模块定义了 AnswerService 类，将本地题库检索、内置匹配规则、LLM 自动沉淀题库和 LLM 提供商 fallback 流程串联起来。
"""

from __future__ import annotations

import time
from typing import Protocol

from .llm.cache import CachedLlmAnswer, LlmAnswerCache, cache_key
from .answer_quality import direct_known_answer, is_cache_safe_answer, repair_model_answer
from .models import CanonicalQuestionRecord, ModelAnswer, QueryResult, QuestionQuery
from .llm.providers import ModelProvider
from .option_labels import canonicalize_label_answer
from .search import LocalQuestionIndex
from .logger import log_event


class QuestionRecordRepository(Protocol):
    """AI 答题沉淀只依赖题库仓储的保存能力。"""

    def save_question_record(self, record: CanonicalQuestionRecord) -> None:
        """保存或更新题库记录。"""
        ...


class AnswerService:
    """答案决议服务类，优先通过本地检索解析答案，并在需要时降级使用大模型。

    支持对本地匹配到的题目补充生成大模型解析，以及在大模型 fallback 时对答案进行一致性校验并沉淀进题库。
    """

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
    ) -> None:
        """初始化答案决议服务。

        Args:
            index: 本地题库索引。
            model_provider: 大模型提供商接口实例（可选）。
            allow_model_fallback: 是否在本地未找到题目时降级请求大模型。
            explain_local_matches: 对于本地检索到的题目，若没有解析，是否调用大模型生成解析。
            allow_known_rules: 是否启用内置高信号规则答案。
            no_local_bank_mode: 是否跳过本地题库与 AI 本地缓存，仅保留规则和模型链路。
            llm_answer_cache: LLM 自动沉淀题库管理实例（可选）。
            trusted_confidence_threshold: AI 题目可自动进入本地命中链路的最低置信度。
            answer_retry_times: AI/联网增强答题链路在异常时的重试次数。
        """
        self.index = index
        self.model_provider = model_provider
        self.allow_model_fallback = allow_model_fallback
        self.explain_local_matches = explain_local_matches
        self.allow_known_rules = allow_known_rules
        self.no_local_bank_mode = no_local_bank_mode
        self.llm_answer_cache = llm_answer_cache
        self.trusted_confidence_threshold = min(max(trusted_confidence_threshold, 0.0), 1.0)
        self.answer_retry_times = max(0, min(int(answer_retry_times), 10))
        self.platform_service: object | None = None
        self.question_repository: QuestionRecordRepository | None = None

    def query(self, query: QuestionQuery) -> QueryResult:
        """查询问题的答案，返回带来源标记的本地结果或明确标识的模型结果。

        决议策略优先级：
        1. 本地精确匹配
        2. 本地预设/固定匹配规则 (direct_known_answer)
        3. 已有的受信任 LLM 自动沉淀题库记录 (CachedLlmAnswer)
        4. 本地模糊匹配
        5. 大模型在线生成降级 (LLM fallback)

        Args:
            query: 问题查询对象。

        Returns:
            QueryResult: 决议后的查询结果。
        """
        # 步骤 1：尝试本地精确匹配（不开启模糊匹配）
        local_result: QueryResult | None = None
        if not self.no_local_bank_mode:
            local_result = self.index.query(query, allow_fuzzy=False)
            if local_result.ok:
                # 如果本地成功匹配，且开启了本地匹配补充大模型解析配置，则调用大模型生成解析
                if self.explain_local_matches and self.model_provider and not local_result.explanation:
                    return self._add_model_explanation(local_result, query)
                return local_result
            if local_result.error_code != "NOT_FOUND":
                return local_result

        # 步骤 2：精确匹配失败，尝试匹配本地内置高信号固定规则
        direct_answer = direct_known_answer(query) if self.allow_known_rules else None
        if direct_answer is not None:
            return self._result_from_direct_answer(query, direct_answer)

        # 步骤 3：尝试匹配已经过多次验证的受信任 LLM 自动沉淀记录
        cached_answer = (
            self.llm_answer_cache.get_trusted(query)
            if self.llm_answer_cache and not self.no_local_bank_mode
            else None
        )
        if cached_answer is not None:
            return self._result_from_cached_answer(query, cached_answer)

        # 步骤 4：尝试本地模糊匹配
        if not self.no_local_bank_mode:
            local_result = self.index.query(query)
            if local_result.ok:
                if self.explain_local_matches and self.model_provider and not local_result.explanation:
                    return self._add_model_explanation(local_result, query)
                return local_result

        # 步骤 5：本地检索与规则均未命中，若配置允许降级，则请求大模型
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
        """获取非敏感的服务运行时配置与状态信息，用于服务验证。

        Returns:
            dict: 包含索引状态、模型提供商状态 and LLM 缓存配置的字典。
        """
        provider_name = self.model_provider.provider_name if self.model_provider else None
        model_status: dict[str, object] = {
            "configured": self.model_provider is not None,
            "provider": provider_name,
            "fallback_enabled": self.allow_model_fallback,
            "explain_local_matches": self.explain_local_matches,
            "answer_retry_times": self.answer_retry_times,
        }
        if self.model_provider is not None:
            # 提取大模型提供商的内部特征字段用于诊断
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
            # 补全解析失败时不影响本地题目的返回，静默失败并返回原结果
            return result
        if model_answer.explanation:
            result.explanation = model_answer.explanation
            result.debug["provider"] = "local-normalized-jsonl+model-explanation"
        return result

    def _model_fallback(self, query: QuestionQuery) -> QueryResult:
        """本地未命中的情况下降级请求大模型获取答案，并记录缓存。"""
        assert self.model_provider is not None
        # 请求前再次校验规则和缓存，防范并发或状态漂移
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
            # 调用大模型并对模型返回的结果进行后处理修复
            model_answer, attempts = self._retry_model_answer(query)
        except Exception as exc:
            # 大模型接口异常时，返回明确的报错结果并标记需要审核
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

        confidence = max(0.0, min(model_answer.confidence, 1.0))
        cache_entry = None
        cache_status = "disabled"
        safe_for_question_bank = is_cache_safe_answer(query, model_answer)
        has_answer_content = bool(
            str(model_answer.candidate_answer or "").strip()
            or str(model_answer.answer_text or "").strip()
        )
        learned_status = (
            "trusted"
            if safe_for_question_bank and confidence >= self.trusted_confidence_threshold
            else "low_confidence"
        )
        learned_record = None
        if has_answer_content:
            learned_record = self._persist_model_answer_record(
                query,
                model_answer,
                status=learned_status,
            )
            if (
                safe_for_question_bank
                and learned_record is not None
                and learned_status == "trusted"
            ):
                self.index.add_or_replace(learned_record)
        # 校验模型答案是否满足内部一致性条件，若安全则尝试进行持久化缓存
        if self.llm_answer_cache is not None and safe_for_question_bank:
            cache_entry = self.llm_answer_cache.record_model_answer(
                query,
                model_answer,
                provider_name=self.model_provider.provider_name,
                force_trusted=learned_status == "trusted" and self.question_repository is not None,
            )
            cache_status = cache_entry.status if cache_entry else "not_cached"
            if cache_entry is not None and cache_entry.status == "trusted":
                self.index.add_or_replace(cache_entry.to_record())
        elif self.llm_answer_cache is not None:
            cache_status = "unsafe_not_cached"
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
                "retry_attempts": str(attempts),
            },
        )

    def _retry_model_answer(self, query: QuestionQuery) -> tuple[ModelAnswer, int]:
        """在 AI/联网增强答题链路异常时按配置次数重试。"""

        assert self.model_provider is not None
        max_attempts = max(1, self.answer_retry_times + 1)
        last_error: Exception | None = None
        attempts = 0
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                answer = self.model_provider.answer(query)
                return repair_model_answer(query, answer), attempt
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                log_event(
                    "answer_retry",
                    {
                        "request_id": query.request_id,
                        "title": query.title,
                        "provider": self.model_provider.provider_name,
                        "attempt": attempt,
                        "max_retries": self.answer_retry_times,
                        "error": str(exc),
                    },
                )
        assert last_error is not None
        setattr(last_error, "stqb_retry_attempts", attempts)
        raise last_error

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
    ):
        """把结构化 AI 答案写入题库仓储，并按状态决定后续是否可命中。"""

        repository = self.question_repository
        if repository is None:
            return None
        candidate = (
            canonicalize_label_answer(query, str(answer.candidate_answer or "").strip())
            or str(answer.candidate_answer or "").strip()
            or str(answer.answer_text or "").strip()
        )
        if not candidate:
            return None
        now = time.time()
        entry = CachedLlmAnswer(
            key=cache_key(query),
            title=query.title,
            question_type=query.question_type,
            options=query.options,
            candidate_answer=candidate,
            answer_text=answer.answer_text,
            explanation=answer.explanation,
            confidence=max(0.0, min(answer.confidence, 1.0)),
            confirmations=1,
            conflicts=0,
            status=status,
            provider_name=self.model_provider.provider_name if self.model_provider else "unknown",
            created_at=now,
            updated_at=now,
        )
        record = entry.to_record()
        try:
            repository.save_question_record(record)
        except Exception:
            return None
        return record
