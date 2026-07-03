"""OpenAI 兼容聊天补全服务提供商。

该模块通过共享 httpx 客户端向任意与 OpenAI API 兼容的 `/chat/completions` 接口发送请求。
支持常规流式与非流式响应解析、输入检索证据（RAG）、提取模型生成的结构化答案以及应对模型输出异常的后备解析策略。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from ...http_client import HttpClientError, normalize_container_loopback_url, request_text
from ...image_ocr import build_ocr_query
from ...input_anomalies import (
    model_answer_indicates_unreadable_image,
    normalize_image_data_urls,
    normalize_image_urls,
)
from ...models import ModelAnswer, QuestionQuery
from ...logger import log_event
from ...question_types import is_open_text_completion
from ..tracing import record_trace
from .openai_answer_parser import (
    answer_field,
    bool_from_env,
    completion_answer_field,
    decode_chat_response,
    int_from_env,
    is_completion_without_options,
    normalize_answer_for_query,
    optional_float,
    parse_plain_text_answer,
    strip_json_fence,
    strip_option_label,
    text_field,
)
from .web_search import WebSearchResult
from ..orchestration.search_augmented import render_search_evidence


@dataclass(slots=True)
class OpenAICompatibleProvider:
    """调用与 OpenAI 兼容的 `/chat/completions` 接口的模型服务提供类。

    该类通过发送特定的系统提示词和用户提示词，促使大模型返回包含候选答案、详细说明及置信度的结构化 JSON 响应。
    """

    base_url: str  # 接口基准地址 (例如 "https://api.openai.com/v1" 或 "http://localhost:11434/v1")
    model: str  # 调用的模型名称 (例如 "gpt-4o", "deepseek-chat")
    api_key: str | None = None  # API 密钥（若接口无需鉴权可为空）
    timeout_seconds: float = 30.0  # 请求超时时长（秒）
    provider_name: str = "openai-compatible"  # 提供商唯一标识名称
    stream: bool = True  # 是否使用流式传输接收响应以提升首字符响应时间
    max_completion_tokens: int = 700  # 最大生成 token 数量限制
    model_id: str = ""  # 平台模型配置记录 ID
    display_name: str = ""  # 平台展示名称

    def __post_init__(self) -> None:
        """规范化容器内访问宿主机服务的基础地址。"""

        self.base_url = normalize_container_loopback_url(self.base_url)

    @classmethod
    def from_env(
        cls,
        *,
        base_url_env: str = "STQB_LLM_BASE_URL",
        model_env: str = "STQB_LLM_MODEL",
        api_key_env: str = "STQB_LLM_API_KEY",
        stream_env: str = "STQB_LLM_STREAM",
        max_tokens_env: str = "STQB_LLM_MAX_COMPLETION_TOKENS",
    ) -> "OpenAICompatibleProvider | None":
        """从环境变量中读取配置并构建 OpenAICompatibleProvider 实例。

        若关键环境变量 (base_url_env 或 model_env) 未配置，则直接返回 None。

        参数:
            base_url_env: 基础 URL 对应的环境变量键名，默认 "STQB_LLM_BASE_URL"。
            model_env: 模型名称对应的环境变量键名，默认 "STQB_LLM_MODEL"。
            api_key_env: API 密钥对应的环境变量键名，默认 "STQB_LLM_API_KEY"。
            stream_env: 流式开关对应的环境变量键名，默认 "STQB_LLM_STREAM"。
            max_tokens_env: 最大 token 数限制对应的环境变量键名，默认 "STQB_LLM_MAX_COMPLETION_TOKENS"。

        返回:
            OpenAICompatibleProvider | None: 成功构建的实例或 None。
        """

        base_url = os.getenv(base_url_env)
        model = os.getenv(model_env)
        if not base_url or not model:
            return None
        return cls(
            base_url=base_url,
            model=model,
            api_key=os.getenv(api_key_env),
            stream=bool_from_env(os.getenv(stream_env), default=True),
            max_completion_tokens=int_from_env(os.getenv(max_tokens_env), default=700),
        )

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """为指定的题目查询获取结构化答案（不带搜索证据）。

        参数:
            query: 题目查询结构体 (QuestionQuery)。

        返回:
            ModelAnswer: 结构化的模型回答。
        """

        return self._answer(query, phase="answer")

    def answer_with_evidence(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...],
    ) -> ModelAnswer:
        """根据提供的网络检索证据片段生成结构化答案（RAG 增强）。

        参数:
            query: 题目查询结构体 (QuestionQuery)。
            evidence: 网络搜索结果的元组。

        返回:
            ModelAnswer: 结构化的模型回答。
        """

        return self._answer(query, evidence=evidence, phase="answer_with_evidence")

    def verify_answer(self, query: QuestionQuery, initial_answer: ModelAnswer) -> ModelAnswer:
        """对已有答案执行一次无证据复核，并返回结构化结果。"""
        return self._answer(query, verification_answer=initial_answer, phase="verify_answer")

    def verify_answer_with_evidence(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...],
        initial_answer: ModelAnswer,
    ) -> ModelAnswer:
        """结合联网证据对已有答案执行复核，并返回结构化结果。"""
        return self._answer(
            query,
            evidence=evidence,
            verification_answer=initial_answer,
            phase="verify_answer_with_evidence",
        )

    def _answer(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...] = (),
        verification_answer: ModelAnswer | None = None,
        phase: str = "answer",
    ) -> ModelAnswer:
        """发送请求并获取模型生成的结构化答案。

        参数:
            query: 题目查询。
            evidence: 外部参考证据元组（选填）。

        返回:
            ModelAnswer: 解析归一化后的模型答案。
        """

        # 构造约束模型输出行为的 System Prompt
        system_prompt = (
            "You are a study assistant. Return only JSON with keys "
            "candidate_answer, answer_text, explanation, confidence, "
            "question_form, reuse_policy, reuse_reason, reuse_confidence. "
            "When options are provided, candidate_answer must use option letters only. "
            "For multiple-choice questions, join letters with #, for example A#C. "
            "Set reuse_policy to reusable for choice, judgement, real blank, calculation, "
            "and deterministic short-answer questions. Set reuse_policy to "
            "non_reusable_open_text only for personalized long-form writing tasks such as "
            "reflections, essays, papers, reports, summaries, reviews, or experiences. "
            "Do not mark a question as non_reusable_open_text merely because words like "
            "essay, report, 作文, or 报告 appear as ordinary nouns in a deterministic question. "
            "If unsure, set confidence below 0.5 and reuse_confidence below 0.5."
        )
        # 如果提供了证据，在 System Prompt 中加入检索依赖提示
        if evidence:
            system_prompt += (
                " Use the provided web evidence before answering. "
                "If evidence conflicts with memory, trust the evidence. "
                "Mention the most relevant evidence number in explanation."
            )
        if verification_answer is not None:
            system_prompt += (
                " Verify the previous answer and correct it if necessary. "
                "Still return only the same JSON object with all required keys."
            )
        prompt = self._render_question(
            query,
            evidence=evidence,
            verification_answer=verification_answer,
        )
        user_content = self._message_content(query, prompt)
        # 构建请求载荷
        payload = {
            "model": self.model,
            "temperature": 0,  # 设为 0 以保证最佳的确定性与复现性
            "stream": self.stream,
            "max_completion_tokens": self.max_completion_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        }
        # 记录模型请求事件
        log_event(
            "model_request",
            {
                "provider": self.provider_name,
                "base_url": self.base_url,
                "model": self.model,
                "stream": self.stream,
                "title": query.title,
                "options_count": len(query.options),
                "evidence_count": len(evidence),
                "image_count": len(
                    normalize_image_data_urls(
                        query.image_data_urls,
                        query.option_image_data_urls.values(),
                    )
                    or normalize_image_urls(query.image_urls, query.option_image_urls.values())
                ),
            },
        )
        started = time.time()
        response_text = ""
        try:
            raw_response = self._post_json(self._chat_url(), payload)
            content = self._response_content(raw_response)
            response_text = content
            # 解析返回的文本为 ModelAnswer
            try:
                answer = self._parse_model_answer(content, query)
            except Exception as exc:
                setattr(exc, "stqb_trace_phase", "model_parse")
                setattr(exc, "stqb_response_preview", content[:1000])
                raise
            elapsed_ms = round((time.time() - started) * 1000, 2)
            if model_answer_indicates_unreadable_image(query, answer) and not phase.endswith(
                "_ocr_fallback"
            ):
                self._record_model_trace(
                    phase=phase,
                    query=query,
                    prompt=prompt,
                    response_text=content,
                    answer=answer,
                    ok=False,
                    error="model returned unreadable image answer",
                    elapsed_ms=elapsed_ms,
                )
                ocr_query = build_ocr_query(query)
                if ocr_query is not None:
                    ocr_answer = self._answer(
                        ocr_query,
                        evidence=evidence,
                        verification_answer=verification_answer,
                        phase=f"{phase}_ocr_fallback",
                    )
                    if ocr_answer.source_query is None:
                        ocr_answer.source_query = ocr_query
                    return ocr_answer
            self._record_model_trace(
                phase=phase,
                query=query,
                prompt=prompt,
                response_text=content,
                answer=answer,
                ok=True,
                elapsed_ms=elapsed_ms,
            )
            # 记录模型响应事件
            log_event(
                "model_response",
                {
                    "provider": self.provider_name,
                    "model": self.model,
                    "candidate_answer": answer.candidate_answer,
                    "confidence": answer.confidence,
                    "content_preview": content[:500],
                },
            )
            return answer
        except Exception as exc:
            elapsed_ms = round((time.time() - started) * 1000, 2)
            trace_phase = str(getattr(exc, "stqb_trace_phase", phase) or phase)
            response_preview = str(
                getattr(exc, "stqb_response_preview", response_text[:1000]) or ""
            )
            self._record_model_trace(
                phase=trace_phase,
                query=query,
                prompt=prompt,
                response_text=response_preview,
                ok=False,
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
            if normalize_image_urls(query.image_urls, (query.title,)) and not phase.endswith(
                "_ocr_fallback"
            ):
                ocr_query = build_ocr_query(query)
                if ocr_query is not None:
                    ocr_answer = self._answer(
                        ocr_query,
                        evidence=evidence,
                        verification_answer=verification_answer,
                        phase=f"{phase}_ocr_fallback",
                    )
                    if ocr_answer.source_query is None:
                        ocr_answer.source_query = ocr_query
                    return ocr_answer
            raise

    def _chat_url(self) -> str:
        """获取聊天补全接口的完整 URL 请求地址。"""
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def _response_content(self, raw_response: dict) -> str:
        """从兼容 OpenAI 的响应体中提取消息内容。"""

        try:
            content = raw_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            error = RuntimeError(f"model provider returned malformed chat response: {exc}")
            setattr(error, "stqb_trace_phase", "model_decode")
            setattr(
                error,
                "stqb_response_preview",
                json.dumps(raw_response, ensure_ascii=False)[:1000],
            )
            raise error from exc
        return str(content or "")

    def _post_json(self, url: str, payload: dict) -> dict:
        """向指定的 URL 发送 POST 请求并返回解析后的 JSON 字典。

        内部会根据环境变量中配置的 LLM 代理服务器自动配置代理。

        参数:
            url: 目标地址。
            payload: JSON 请求载荷字典。

        返回:
            dict: 成功时返回的响应 JSON。
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response_body = request_text(
                "POST",
                url,
                headers=headers,
                json_body=payload,
                timeout=self.timeout_seconds,
                proxy_env="STQB_LLM_PROXY",
            )
            try:
                return decode_chat_response(response_body)
            except (json.JSONDecodeError, RuntimeError) as exc:
                log_event(
                    "model_error",
                    {
                        "provider": self.provider_name,
                        "url": url,
                        "error": str(exc),
                        "response_preview": response_body[:1000],
                    },
                )
                error = RuntimeError(f"model provider returned invalid response: {exc}")
                setattr(error, "stqb_trace_phase", "model_decode")
                setattr(error, "stqb_response_preview", response_body[:1000])
                raise error from exc
        except HttpClientError as exc:
            detail = str(exc)
            log_event("model_error", {"provider": self.provider_name, "url": url, "error": detail})
            error = RuntimeError(f"model provider request failed: {detail}")
            setattr(error, "stqb_trace_phase", "model_request")
            setattr(error, "stqb_response_preview", getattr(exc, "response_body", "")[:1000])
            raise error from exc

    def _parse_model_answer(self, content: str, query: QuestionQuery | None = None) -> ModelAnswer:
        """从模型输出的字符串中提取结构化的 ModelAnswer 实例。

        若模型未按指令输出有效 JSON，将进入文本匹配规则模式进行容错解析。

        参数:
            content: 模型原始响应字符串。
            query: 当前题目查询结构体（用于映射或过滤选项）。

        返回:
            ModelAnswer: 结构化题目答案。
        """
        # 清除可能带有的 Markdown 语法块 ```json 围栏
        stripped = strip_json_fence(content)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            # 进入纯文本容错解析机制
            answer = parse_plain_text_answer(stripped)
            return normalize_answer_for_query(answer, query)
        confidence = float(payload.get("confidence") or 0.0)
        candidate_answer = answer_field(payload.get("candidate_answer"))
        answer_text = text_field(payload.get("answer_text"))
        reuse_confidence = optional_float(payload.get("reuse_confidence"))
        if is_completion_without_options(query):
            candidate_answer = (
                answer_text
                if answer_text and is_open_text_completion(query)
                else completion_answer_field(
                    payload.get("candidate_answer"), payload.get("answer_text")
                )
            )
        answer = ModelAnswer(
            candidate_answer=candidate_answer,
            answer_text=answer_text,
            explanation=(
                str(payload.get("explanation")).strip()
                if payload.get("explanation") is not None
                and str(payload.get("explanation")).strip()
                else None
            ),
            confidence=max(0.0, min(confidence, 1.0)),
            question_form=text_field(payload.get("question_form")),
            reuse_policy=text_field(payload.get("reuse_policy")),
            reuse_reason=text_field(payload.get("reuse_reason")),
            reuse_confidence=(
                max(0.0, min(reuse_confidence, 1.0))
                if reuse_confidence is not None
                else None
            ),
        )
        return normalize_answer_for_query(answer, query)

    def _record_model_trace(
        self,
        *,
        phase: str,
        query: QuestionQuery,
        prompt: str,
        response_text: str = "",
        answer: ModelAnswer | None = None,
        ok: bool,
        error: str = "",
        elapsed_ms: float,
    ) -> None:
        """记录模型调用追溯，不让追溯失败影响答题主链路。"""

        record_trace(
            phase=phase,
            model_id=self.model_id,
            model_name=self.display_name or self.model,
            base_url=self.base_url,
            provider=self.provider_name,
            question_title=query.title,
            prompt=prompt,
            response_text=response_text[:4000],
            candidate_answer=answer.candidate_answer if answer else None,
            confidence=answer.confidence if answer else 0.0,
            ok=ok,
            error=error,
            elapsed_ms=elapsed_ms,
        )

    def _render_question(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...] = (),
        verification_answer: ModelAnswer | None = None,
    ) -> str:
        """将题目、选项和背景证据渲染为单条提示词字符串。

        参数:
            query: 题目结构体。
            evidence: 检索出的网页证据元组。

        返回:
            str: 格式化后的 Prompt 文本。
        """
        lines = [f"Question type: {query.question_type}", f"Question: {query.title}"]
        if query.options:
            lines.append("Options:")
            labels = ("A", "B", "C", "D", "E", "F")
            lines.extend(
                f"{label}. {strip_option_label(option)}"
                for label, option in zip(labels, query.options, strict=False)
            )
        if evidence:
            lines.append("Web evidence:")
            lines.append(render_search_evidence(evidence))
        if verification_answer is not None:
            lines.append("Previous answer:")
            lines.append(f"candidate_answer: {verification_answer.candidate_answer or ''}")
            lines.append(f"answer_text: {verification_answer.answer_text or ''}")
            lines.append(f"explanation: {verification_answer.explanation or ''}")
            lines.append(f"confidence: {verification_answer.confidence}")
        return "\n".join(lines)

    def _message_content(self, query: QuestionQuery, prompt: str) -> str | list[dict]:
        """按 OpenAI 兼容多模态格式构造用户消息内容。"""

        image_refs = normalize_image_data_urls(
            query.image_data_urls,
            query.option_image_data_urls.values(),
        ) or normalize_image_urls(query.image_urls, query.option_image_urls.values())
        if not image_refs:
            return prompt
        content: list[dict] = [{"type": "text", "text": prompt}]
        for item in image_refs[:6]:
            content.append({"type": "image_url", "image_url": {"url": item}})
        return content


# 为兼容现有测试与局部旧调用，保留最薄私有别名层。
_decode_chat_response = decode_chat_response
