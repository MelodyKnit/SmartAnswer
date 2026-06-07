"""OpenAI 兼容聊天补全服务提供商。

该模块通过共享 httpx 客户端向任意与 OpenAI API 兼容的 `/chat/completions` 接口发送请求。
支持常规流式与非流式响应解析、输入检索证据（RAG）、提取模型生成的结构化答案以及应对模型输出异常的后备解析策略。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from ..http_client import HttpClientError, request_text
from ..models import ModelAnswer, QuestionQuery
from ..option_labels import canonicalize_label_answer
from ..runtime_log import log_event
from .search_augmented import render_search_evidence
from .web_search import WebSearchResult


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
            stream=_bool_from_env(os.getenv(stream_env), default=True),
            max_completion_tokens=_int_from_env(os.getenv(max_tokens_env), default=700),
        )

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """为指定的题目查询获取结构化答案（不带搜索证据）。

        参数:
            query: 题目查询结构体 (QuestionQuery)。

        返回:
            ModelAnswer: 结构化的模型回答。
        """

        return self._answer(query)

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

        return self._answer(query, evidence=evidence)

    def _answer(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...] = (),
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
            "candidate_answer, answer_text, explanation, confidence. "
            "When options are provided, candidate_answer must use option letters only. "
            "For multiple-choice questions, join letters with #, for example A#C. "
            "If unsure, set confidence below 0.5."
        )
        # 如果提供了证据，在 System Prompt 中加入检索依赖提示
        if evidence:
            system_prompt += (
                " Use the provided web evidence before answering. "
                "If evidence conflicts with memory, trust the evidence. "
                "Mention the most relevant evidence number in explanation."
            )
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
                    "content": self._render_question(query, evidence=evidence),
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
            },
        )
        raw_response = self._post_json(self._chat_url(), payload)
        content = raw_response["choices"][0]["message"]["content"]
        # 解析返回的文本为 ModelAnswer
        answer = self._parse_model_answer(content, query)
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

    def _chat_url(self) -> str:
        """获取聊天补全接口的完整 URL 请求地址。"""
        return f"{self.base_url.rstrip('/')}/chat/completions"

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
                return _decode_chat_response(response_body)
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
                raise RuntimeError(f"model provider returned invalid response: {exc}") from exc
        except HttpClientError as exc:
            detail = str(exc)
            log_event("model_error", {"provider": self.provider_name, "url": url, "error": detail})
            raise RuntimeError(f"model provider request failed: {detail}") from exc

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
        stripped = _strip_json_fence(content)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            # 进入纯文本容错解析机制
            answer = _parse_plain_text_answer(stripped)
            return _normalize_answer_for_query(answer, query)
        confidence = float(payload.get("confidence") or 0.0)
        candidate_answer = _answer_field(payload.get("candidate_answer"))
        answer_text = _text_field(payload.get("answer_text"))
        if _is_completion_without_options(query):
            candidate_answer = _completion_answer_field(payload.get("candidate_answer"), payload.get("answer_text"))
        answer = ModelAnswer(
            candidate_answer=candidate_answer,
            answer_text=answer_text,
            explanation=_optional_string(payload.get("explanation")),
            confidence=max(0.0, min(confidence, 1.0)),
        )
        return _normalize_answer_for_query(answer, query)

    def _render_question(
        self,
        query: QuestionQuery,
        evidence: tuple[WebSearchResult, ...] = (),
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
                f"{label}. {_strip_option_label(option)}"
                for label, option in zip(labels, query.options, strict=False)
            )
        if evidence:
            lines.append("Web evidence:")
            lines.append(render_search_evidence(evidence))
        return "\n".join(lines)


def _strip_json_fence(content: str) -> str:
    """去除 Markdown 格式的代码块围栏 (e.g. ```json ... ```)。"""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _optional_string(value: object) -> str | None:
    """将普通对象安全转换为去除首尾空格后的字符串或 None。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _answer_field(value: object) -> str | None:
    """将 candidate_answer 字段值转换为字符串。

    若其是一个数组（可能是多选题），则用 "#" 连接。
    """
    if isinstance(value, (list, tuple)):
        parts = [_optional_string(item) for item in value]
        return "#".join(part for part in parts if part)
    return _optional_string(value)


def _text_field(value: object) -> str | None:
    """将 answer_text 字段值转换为字符串。

    若其是一个数组，则用中文分号 "；" 连接。
    """
    if isinstance(value, (list, tuple)):
        parts = [_optional_string(item) for item in value]
        return "；".join(part for part in parts if part)
    return _optional_string(value)


def _completion_answer_field(candidate_value: object, answer_text_value: object) -> str | None:
    """Encode multi-blank completion answers as a JSON array string for OCS."""
    for value in (candidate_value, answer_text_value):
        if isinstance(value, (list, tuple)):
            parts = [_optional_string(item) for item in value]
            normalized = [part for part in parts if part]
            if normalized:
                return json.dumps(normalized, ensure_ascii=False)
    return _answer_field(candidate_value) or _text_field(answer_text_value)


def _parse_plain_text_answer(content: str) -> ModelAnswer:
    """尽力而为的解析器，用于处理模型忽略 JSON 指令直接输出文本的情况。

    通过正则表达式识别答案前缀并提取大写字母标号（A-F）；支持对错判断题识别。
    """

    normalized = content.strip()
    # 使用正则表达式匹配常见的 “答案是 A”、“Answer: B” 等格式的指示信息
    choice_match = re.search(
        r"(?:答案|answer|选项)?\s*[:：是为]?\s*([A-F](?:[#、,，;；\s]*[A-F]){0,7})\b",
        normalized,
        re.IGNORECASE,
    )
    if choice_match:
        answer = choice_match.group(1).upper()
        return ModelAnswer(
            candidate_answer=answer,
            answer_text=answer,
            explanation=normalized,
            confidence=0.45,  # 文本启发式识别，设置较低的置信度值
        )
    # 处理判断题（正确/对）
    if any(token in normalized for token in ("正确", "对", "true", "True", "TRUE")):
        return ModelAnswer("true", "正确", normalized, 0.4)
    # 处理判断题（错误/错）
    if any(token in normalized for token in ("错误", "错", "false", "False", "FALSE")):
        return ModelAnswer("false", "错误", normalized, 0.4)
    return ModelAnswer(None, None, normalized or None, 0.0)


def _normalize_answer_for_query(answer: ModelAnswer, query: QuestionQuery | None) -> ModelAnswer:
    """根据查询的具体内容和选项列表，对模型返回的答案进行映射与过滤。

    例如将模型给出的原始选项文本内容映射回字母标签 (A/B/C...)。
    """
    if _is_completion_without_options(query):
        return answer
    if not query or not query.options or not answer.candidate_answer:
        return answer

    normalized_candidate = _candidate_to_labels(answer.candidate_answer, query)
    if not normalized_candidate:
        return answer
    if normalized_candidate != answer.candidate_answer:
        log_event(
            "model_answer_normalized",
            {
                "title": query.title,
                "question_type": query.question_type,
                "original_candidate": answer.candidate_answer,
                "normalized_candidate": normalized_candidate,
            },
        )

    rebuilt_answer_text = _answer_text_from_labels(normalized_candidate, query)
    answer_text = rebuilt_answer_text or answer.answer_text
    return ModelAnswer(
        candidate_answer=normalized_candidate,
        answer_text=answer_text,
        explanation=answer.explanation,
        confidence=answer.confidence,
    )


def _candidate_to_labels(candidate_answer: str, query: QuestionQuery) -> str | None:
    """将候选答案标准化为大写的标签选项（如 "A"、"A#B" 等）。"""
    compact = candidate_answer.strip().upper().replace(" ", "")
    # 格式已经是 A#B 类的直接匹配校验
    if re.fullmatch(r"[A-F](?:#[A-F])*", compact):
        normalized = canonicalize_label_answer(query, compact)
        if normalized:
            return normalized
    # 处理没有井号的连续选项（如多选题 "ABC" 转换为 "A#B#C"）
    if query.question_type.lower() in {"multiple", "multi", "多选", "多选题"} and re.fullmatch(r"[A-F]{2,}", compact):
        normalized = canonicalize_label_answer(query, compact)
        if normalized:
            return normalized

    # 如果模型返回了选项的完整文本，则逐个匹配转换
    mapped: list[str] = []
    for part in _split_candidate_parts(candidate_answer):
        label = _part_to_label(part, query)
        if not label:
            return None
        mapped.append(label)
    if not mapped:
        return None
    return canonicalize_label_answer(query, "#".join(mapped))


def _is_completion_without_options(query: QuestionQuery | None) -> bool:
    if query is None or query.options:
        return False
    normalized_type = (query.question_type or "").strip().lower()
    title = (query.title or "").strip()
    return (
        normalized_type in {"completion", "blank", "fill", "填空", "填空题"}
        or title.startswith("填空题")
        or "____" in title
        or "___" in title
    )


def _split_candidate_parts(candidate_answer: str) -> list[str]:
    """通过各种常用分隔符切分候选答案文本。"""
    return [
        part.strip()
        for part in re.split(r"[#;,，、；\n]+", candidate_answer)
        if part.strip()
    ]


def _part_to_label(part: str, query: QuestionQuery) -> str | None:
    """将切分后的单个答案子段转换为相对应的选项字母标签。"""
    labels = ("A", "B", "C", "D", "E", "F")
    compact = part.strip().upper()
    # 如果已是单字符的合法选项标签直接返回
    if re.fullmatch(r"[A-F]", compact) and labels.index(compact) < len(query.options):
        return compact

    # 若是具体文本，则尝试与选项做归一化文本匹配
    normalized_part = _normalize_option_text(part)
    for label, option in zip(labels, query.options, strict=False):
        normalized_option = _normalize_option_text(option)
        if normalized_part == normalized_option:
            return label
    return None


def _answer_text_from_labels(candidate_answer: str, query: QuestionQuery) -> str | None:
    """根据选项标签（如 "A#B"），反向拼接对应的题目选项文本。"""
    labels = ("A", "B", "C", "D", "E", "F")
    option_map = {
        label: _strip_option_label(option)
        for label, option in zip(labels, query.options, strict=False)
    }
    parts = [option_map.get(label) for label in candidate_answer.split("#")]
    texts = [part for part in parts if part]
    return "；".join(texts) if texts else None


def _strip_option_label(option: str) -> str:
    """剥离选项开头自带的类似 "A."、"B、" 等前缀标号。"""
    return re.sub(r"^\s*[A-Fa-f][\.、．:：]\s*", "", option).strip()


def _normalize_option_text(option: str) -> str:
    """对选项文本进行清洗去空，用于文本匹配比对。"""
    return re.sub(r"\s+", "", _strip_option_label(option)).lower()


def _decode_chat_response(response_body: str) -> dict:
    """对接口返回的数据体进行解码。

    若内容是以 `data:` 开头的 SSE 事件流，则采用流式合并解析，否则直接解析为 JSON。
    """
    stripped = response_body.lstrip()
    if stripped.startswith("data:"):
        return _decode_streaming_chat_response(response_body)
    return json.loads(response_body)


def _decode_streaming_chat_response(response_body: str) -> dict:
    """从流式 SSE 的多行文本块中解析并重组完整的对话生成结果。"""
    content_parts: list[str] = []
    for event_payload in _iter_sse_payloads(response_body):
        if event_payload == "[DONE]":
            continue
        try:
            chunk = json.loads(event_payload)
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices") or ():
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                content_parts.append(str(content))
            message = choice.get("message") or {}
            message_content = message.get("content")
            if message_content:
                content_parts.append(str(message_content))

    content = "".join(content_parts).strip()
    if not content:
        raise RuntimeError("streaming model response contained no answer content")
    # 拼装回非流式的标准响应 JSON 字典格式
    return {"choices": [{"message": {"content": content}}]}


def _iter_sse_payloads(response_body: str) -> list[str]:
    """遍历 SSE 响应，过滤并提取 `data:` 行后面的负载内容。"""
    payloads: list[str] = []
    current: list[str] = []
    for raw_line in response_body.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                payloads.append("\n".join(current))
                current = []
            continue
        if line.startswith(":"):  # 忽略注释行/心跳行
            continue
        if line.startswith("data:"):
            current.append(line.removeprefix("data:").strip())
    if current:
        payloads.append("\n".join(current))
    return payloads


def _bool_from_env(value: str | None, *, default: bool) -> bool:
    """从环境变量字符串解析布尔值。"""
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _int_from_env(value: str | None, *, default: int) -> int:
    """从环境变量字符串解析正整数。"""
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
