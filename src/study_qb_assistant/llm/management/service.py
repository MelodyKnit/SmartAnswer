"""平台侧大模型配置、连通性测试与调用追溯服务。"""

from __future__ import annotations

import json
import secrets
import time
from threading import RLock

from ..config import service as llm_config_service
from .records import LlmCallTraceRecord


class LlmManagementService:
    """封装大模型配置、连通性测试与调用追溯。"""

    def __init__(self, repository, lock: RLock) -> None:
        self.repository = repository
        self.lock = lock

    def list_models(self, *, reveal_secret: bool = False) -> list[dict]:
        """列出所有大模型配置。"""

        return llm_config_service.list_llm_models(
            self.repository,
            self.lock,
            reveal_secret=reveal_secret,
        )

    def get_model(self, model_id: str, *, reveal_secret: bool = False) -> dict:
        """读取单个大模型配置。"""

        return llm_config_service.get_llm_model(
            self.repository,
            self.lock,
            model_id,
            reveal_secret=reveal_secret,
        )

    def create_model(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        role: str = "backup",
        priority: int = 100,
        stream: bool = True,
        max_completion_tokens: int = 700,
        timeout_seconds: float = 30.0,
        status: str = "active",
    ) -> dict:
        """新增大模型配置。"""

        return llm_config_service.create_llm_model(
            self.repository,
            self.lock,
            name=name,
            base_url=base_url,
            model=model,
            api_key=api_key,
            role=role,
            priority=priority,
            stream=stream,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            status=status,
        )

    def update_model(self, model_id: str, values: dict) -> dict:
        """更新大模型配置。"""

        return llm_config_service.update_llm_model(
            self.repository,
            self.lock,
            model_id,
            values,
        )

    def delete_model(self, model_id: str) -> bool:
        """删除大模型配置。"""

        return llm_config_service.delete_llm_model(self.repository, self.lock, model_id)

    def active_models(self):
        """返回可参与主备链的大模型配置。"""

        return llm_config_service.active_llm_models(self.repository, self.lock)

    def test_model(self, model_id: str) -> dict:
        """测试指定大模型配置的连通性与接口解析。"""

        from ..prompts import render_prompt
        from ..providers.openai_compatible import OpenAICompatibleProvider
        from study_qb_assistant.questions.models import QuestionQuery

        model_dict = self.get_model(model_id, reveal_secret=True)
        provider = OpenAICompatibleProvider(
            base_url=model_dict["base_url"],
            model=model_dict["model"],
            api_key=model_dict["api_key"] or None,
            stream=model_dict["stream"],
            max_completion_tokens=model_dict["max_completion_tokens"],
            timeout_seconds=model_dict["timeout_seconds"],
            model_id=model_id,
            display_name=model_dict["name"],
        )

        query = QuestionQuery(
            title=render_prompt("llm_connection_test_user.jinja"),
            options=("A", "B"),
            question_type="single",
        )

        t0 = time.time()
        try:
            res = provider.answer(query)
            elapsed = (time.time() - t0) * 1000
            return {
                "ok": True,
                "elapsed_ms": elapsed,
                "candidate_answer": res.candidate_answer,
                "answer_text": res.answer_text,
                "explanation": res.explanation,
                "confidence": res.confidence,
            }
        except Exception as exc:
            elapsed = (time.time() - t0) * 1000
            return {
                "ok": False,
                "elapsed_ms": elapsed,
                "error": str(exc),
            }

    def save_call_trace(self, payload: dict) -> None:
        """落库一条 LLM 调用追溯，失败不影响答题主流程。"""

        try:
            record = LlmCallTraceRecord(
                trace_id=str(payload.get("trace_id") or secrets.token_hex(12)),
                request_id=str(payload.get("request_id") or ""),
                phase=str(payload.get("phase") or ""),
                model_id=str(payload.get("model_id") or payload.get("model_name") or ""),
                model_name=str(payload.get("model_name") or payload.get("model_id") or ""),
                base_url=str(payload.get("base_url") or ""),
                provider=str(payload.get("provider") or ""),
                question_title=str(payload.get("question_title") or ""),
                prompt=str(payload.get("prompt") or payload.get("question_title") or ""),
                evidence=json.dumps(payload.get("evidence") or [], ensure_ascii=False),
                response_text=str(payload.get("response_text") or payload.get("response") or ""),
                candidate_answer=(
                    str(payload["candidate_answer"]) if payload.get("candidate_answer") else None
                ),
                confidence=float(payload.get("confidence") or 0.0),
                ok=bool(payload.get("ok", True)),
                error=str(payload.get("error") or ""),
                elapsed_ms=float(payload.get("elapsed_ms") or payload.get("latency_ms") or 0.0),
                created_at=float(payload.get("created_at") or time.time()),
            )
            self.repository.save_llm_call_trace(record)
        except Exception:
            return

    def list_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按条件分页读取 LLM 调用追溯。"""

        with self.lock:
            return [
                item.to_dict()
                for item in self.repository.list_llm_call_traces(
                    request_id=request_id,
                    model_id=model_id,
                    phase=phase,
                    limit=limit,
                    offset=offset,
                )
            ]

    def count_call_traces(
        self,
        *,
        request_id: str = "",
        model_id: str = "",
        phase: str = "",
    ) -> int:
        """统计 LLM 调用追溯数量。"""

        with self.lock:
            return self.repository.count_llm_call_traces(
                request_id=request_id,
                model_id=model_id,
                phase=phase,
            )

    def call_stats(self) -> list[dict]:
        """按模型聚合 LLM 调用统计。"""

        with self.lock:
            return self.repository.llm_call_stats()
