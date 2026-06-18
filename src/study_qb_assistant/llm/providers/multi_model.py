"""多模型主备自动降级提供者。

把多个 `OpenAICompatibleProvider` 按优先级串成一条主备链：依次尝试，前一个抛错时
自动切换到下一个，并记录一条 failover 追溯。对外暴露与单个提供者一致的接口
（answer / answer_with_evidence / verify_answer / verify_answer_with_evidence 以及
model / stream / max_completion_tokens 等属性），因此可被 SearchAugmentedModelProvider
透明包装。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..tracing import record_trace
from ...models import ModelAnswer, QuestionQuery
from ...logger import log_event
from .openai_compatible import OpenAICompatibleProvider
from .web_search import WebSearchResult


@dataclass(slots=True)
class MultiModelProvider:
    """按优先级编排多个 OpenAI 兼容模型，提供主备自动降级。"""

    members: tuple[OpenAICompatibleProvider, ...]
    provider_name: str = "multi-model"
    _last_used: OpenAICompatibleProvider | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("MultiModelProvider requires at least one member provider")

    @property
    def primary(self) -> OpenAICompatibleProvider:
        """返回当前优先级最高的模型（主用）。"""
        return self.members[0]

    @property
    def model(self) -> str | None:
        """对外暴露当前主用模型名，兼容旧的 status/诊断字段。"""
        active = self._last_used or self.primary
        return getattr(active, "model", None)

    @property
    def stream(self) -> bool | None:
        return getattr(self.primary, "stream", None)

    @property
    def max_completion_tokens(self) -> int | None:
        return getattr(self.primary, "max_completion_tokens", None)

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        return self._run(lambda member: member.answer(query), query=query, phase="answer")

    def answer_with_evidence(
        self, query: QuestionQuery, evidence: tuple[WebSearchResult, ...]
    ) -> ModelAnswer:
        return self._run(
            lambda member: member.answer_with_evidence(query, evidence),
            query=query,
            phase="answer_with_evidence",
        )

    def verify_answer(self, query: QuestionQuery, proposed_answer: ModelAnswer) -> ModelAnswer:
        return self._run(
            lambda member: member.verify_answer(query, proposed_answer),
            query=query,
            phase="verify_answer",
        )

    def verify_answer_with_evidence(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...],
        proposed_answer: ModelAnswer,
    ) -> ModelAnswer:
        return self._run(
            lambda member: member.verify_answer_with_evidence(query, evidence, proposed_answer),
            query=query,
            phase="verify_answer_with_evidence",
        )

    def _run(self, call, *, query: QuestionQuery, phase: str) -> ModelAnswer:
        """依次尝试每个成员模型，前者失败则降级到下一个。"""
        last_error: Exception | None = None
        for index, member in enumerate(self.members):
            try:
                answer = call(member)
                self._last_used = member
                return answer
            except Exception as exc:  # noqa: BLE001 - 需要捕获任意提供者异常以降级
                last_error = exc
                next_member = self.members[index + 1] if index + 1 < len(self.members) else None
                log_event(
                    "model_failover",
                    {
                        "phase": phase,
                        "failed_model": getattr(member, "model", ""),
                        "failed_model_id": getattr(member, "model_id", ""),
                        "next_model": getattr(next_member, "model", "") if next_member else "",
                        "error": str(exc),
                    },
                )
                record_trace(
                    phase="failover",
                    model_id=getattr(member, "model_id", ""),
                    model_name=getattr(member, "display_name", "") or getattr(member, "model", ""),
                    base_url=getattr(member, "base_url", ""),
                    provider=self.provider_name,
                    question_title=query.title,
                    prompt=f"phase={phase}; 主备降级，切换到下一个模型："
                    f"{getattr(next_member, 'model', '') if next_member else '（无更多备用）'}",
                    ok=False,
                    error=str(exc),
                )
                continue
        # 所有成员都失败，抛出最后一次错误以保持原有的 MODEL_ERROR 语义
        if last_error is not None:
            raise last_error
        raise RuntimeError("no model provider available")
