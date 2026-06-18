"""基于网络检索证据增强大模型解答（RAG）的装饰器。

该模块实现了一个包装器类，它将网络搜索引擎（SearchProvider）与大模型生成器（ModelProvider）相结合。
通过在调用模型回答前先从网络中检索相关信息，并将这些检索结果拼接在 Prompt 中作为证据，提升模型作答的准确率与时效性。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from collections import defaultdict
import re
import time
from typing import cast

from ...models import ModelAnswer, QuestionQuery
from ..tracing import record_trace
from ...logger import log_event
from ..providers.base import ModelProvider
from ..providers.web_search import WebSearchProvider, WebSearchResult, preferred_domain_score


@dataclass(slots=True)
class SearchAugmentedModelProvider:
    """使用网络搜索证据检索服务来包装底层大模型提供商的增强型解答类。

    它拦截了原有的 `answer` 调用，首先通过绑定的 `search_provider` 执行实时检索，
    再将检索到的前 k 个结果作为额外知识（evidence）传递给支持证据增强的大模型生成器。
    """

    model_provider: ModelProvider  # 底层的大语言模型提供商实例
    search_provider: WebSearchProvider  # 绑定的网络搜索服务提供商实例
    top_k: int = 5  # 最大检索网络证据片段数量，默认为 5
    provider_name: str = "openai-compatible+web-search"  # 组合提供商名称
    search_first: bool = True  # 是否优先搜索后回答
    consensus_confidence_floor: float = 0.985  # 无证据直答可直接接受的最低置信度
    search_first_types: tuple[str, ...] = ("multiple", "completion")  # 这些题型默认先检索再作答
    self_consistency_repeats: int = 1  # 低稳定度场景的重复作答次数
    _search_cache: dict[str, tuple[WebSearchResult, ...]] = field(default_factory=dict)
    search_cache_path: str | None = None  # 可选的持久化搜索缓存路径
    _persistent_cache_loaded: bool = field(default=False, init=False, repr=False)
    search_cache_version: str = "v2"

    @property
    def model(self) -> str | None:
        """获取底层模型名称（如果底层模型提供商有定义）。"""
        return getattr(self.model_provider, "model", None)

    @property
    def stream(self) -> bool | None:
        """获取底层模型是否支持流式返回的配置（如果定义）。"""
        return getattr(self.model_provider, "stream", None)

    @property
    def max_completion_tokens(self) -> int | None:
        """获取底层模型生成的最大 token 数量配置（如果定义）。"""
        return getattr(self.model_provider, "max_completion_tokens", None)

    @property
    def search_enabled(self) -> bool:
        """指示该组合提供者当前已启用搜索增强。"""
        return True

    @property
    def search_provider_name(self) -> str:
        """获取搜索引擎提供商的名称。"""
        return self.search_provider.provider_name

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """先对题目执行网络检索，然后再使用检索证据生成最终的结构化答案。

        若底层大模型生成器不支持 `answer_with_evidence` 方法，或者检索没有返回任何结果，
        则直接使用底层生成器的默认 `answer` 方法解答。

        参数:
            query: 题目查询结构体 (QuestionQuery)。

        返回:
            ModelAnswer: 检索增强后生成的模型答案。
        """

        normalized_type = (query.question_type or "").strip().lower()
        if self.search_first or normalized_type in self.search_first_types:
            return self._search_first_answer(query)
        return self._model_first_answer(query)

    def _search_first_answer(self, query: QuestionQuery) -> ModelAnswer:
        """优先搜索，再让模型作答。"""
        results = self._search(query)
        extracted = extract_completion_answer_from_evidence(query, results)
        if extracted is not None:
            return extracted
        answer_with_evidence = getattr(self.model_provider, "answer_with_evidence", None)
        if answer_with_evidence is None or not callable(answer_with_evidence) or not results:
            answer = self.model_provider.answer(query)
            return self._verify_without_evidence(query, answer)
        answer = self._run_consensus(
            lambda: self._verify_with_evidence(
                query, results, answer_with_evidence(query, results)
            ),
            repeats=self._effective_repeats(query),
        )
        return answer

    def _model_first_answer(self, query: QuestionQuery) -> ModelAnswer:
        """先让模型作答，再按需要升级到浏览器/联网搜索。"""
        answer = self.model_provider.answer(query)
        verified = self._verify_without_evidence(query, answer)
        if self._can_accept_without_search(query, verified):
            second = self._verify_without_evidence(query, self.model_provider.answer(query))
            if self._same_answer(verified, second):
                return verified
        results = self._search(query)
        if not results:
            return verified
        extracted = extract_completion_answer_from_evidence(query, results)
        if extracted is not None:
            return extracted
        answer_with_evidence = getattr(self.model_provider, "answer_with_evidence", None)
        if answer_with_evidence is None or not callable(answer_with_evidence):
            return verified
        evidence_answer = self._run_consensus(
            lambda: self._verify_with_evidence(
                query, results, answer_with_evidence(query, results)
            ),
            repeats=self._effective_repeats(query),
        )
        return self._verify_with_evidence(query, results, evidence_answer)

    def _search(self, query: QuestionQuery) -> tuple[WebSearchResult, ...]:
        """执行联网搜索并记录日志。"""
        self._ensure_persistent_cache_loaded()
        cache_key = self._search_cache_key(query)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return cached
        started = time.time()
        results = self.search_provider.search(query, top_k=self.top_k)
        evidence_payload = [
            {
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet[:220],
                "source": result.source,
            }
            for result in results[: self.top_k]
        ]
        log_event(
            "web_search_results",
            {
                "provider": self.search_provider.provider_name,
                "title": query.title,
                "result_count": len(results),
                "results": evidence_payload,
            },
        )
        record_trace(
            phase="web_search",
            provider=self.search_provider.provider_name,
            question_title=query.title,
            prompt=f"web search query: {query.title}",
            evidence=evidence_payload,
            response_text=f"命中 {len(results)} 条联网证据",
            ok=True,
            elapsed_ms=round((time.time() - started) * 1000, 2),
        )
        self._search_cache[cache_key] = results
        try:
            self._save_persistent_cache()
        except Exception:
            pass
        return results

    def _verify_without_evidence(self, query: QuestionQuery, answer: ModelAnswer) -> ModelAnswer:
        """在无外部证据时执行模型自检。"""
        verifier = getattr(self.model_provider, "verify_answer", None)
        if verifier is None or not callable(verifier):
            return answer
        try:
            verified = verifier(query, answer)
        except Exception:
            return answer
        return verified if verified.candidate_answer else answer

    def _verify_with_evidence(
        self,
        query: QuestionQuery,
        results: tuple[WebSearchResult, ...],
        answer: ModelAnswer,
    ) -> ModelAnswer:
        """在有证据时执行二次校验。"""
        verifier = getattr(self.model_provider, "verify_answer_with_evidence", None)
        if verifier is None or not callable(verifier):
            return answer
        try:
            verified = verifier(query, results, answer)
        except Exception:
            return self._verify_without_evidence(query, answer)
        return verified if verified.candidate_answer else answer

    def _can_accept_without_search(self, query: QuestionQuery, answer: ModelAnswer) -> bool:
        """判断当前题目是否可以在无证据状态下先尝试一致性校验。"""
        normalized_type = (query.question_type or "").strip().lower()
        if normalized_type in {"multiple", "completion"}:
            return False
        return answer.confidence >= self.consensus_confidence_floor

    def _same_answer(self, left: ModelAnswer, right: ModelAnswer) -> bool:
        """判断两次模型答案是否一致。"""
        return (left.candidate_answer or "").strip() == (right.candidate_answer or "").strip() and (
            left.answer_text or ""
        ).strip() == (right.answer_text or "").strip()

    def _search_cache_key(self, query: QuestionQuery) -> str:
        """为搜索结果缓存构建稳定键。"""
        option_key = "\n".join(query.options)
        return f"{self.search_cache_version}\n{query.question_type}\n{query.title}\n{option_key}"

    def _ensure_persistent_cache_loaded(self) -> None:
        """按需加载落盘的搜索缓存。"""
        if self._persistent_cache_loaded:
            return
        self._persistent_cache_loaded = True
        if not self.search_cache_path:
            return
        path = Path(self.search_cache_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for key, items in payload.items():
            if not isinstance(items, list):
                continue
            results = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                results.append(
                    WebSearchResult(
                        title=str(item.get("title") or ""),
                        url=str(item.get("url") or ""),
                        snippet=str(item.get("snippet") or ""),
                        source=str(item.get("source") or ""),
                    )
                )
            self._search_cache[str(key)] = tuple(results)

    def _save_persistent_cache(self) -> None:
        """把搜索缓存写入磁盘，便于分段回放复用。"""
        if not self.search_cache_path:
            return
        path = Path(self.search_cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: [
                {
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet,
                    "source": item.source,
                }
                for item in results
            ]
            for key, results in self._search_cache.items()
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _effective_repeats(self, query: QuestionQuery) -> int:
        """按题型决定是否启用自一致性重复作答。"""
        normalized_type = (query.question_type or "").strip().lower()
        if normalized_type in {"completion", "multiple", "填空题", "多选题"}:
            return max(1, self.self_consistency_repeats)
        return 1

    def _run_consensus(self, strategy, *, repeats: int) -> ModelAnswer:
        """执行多次作答并按多数票选择结果。"""
        first = strategy()
        if repeats <= 1:
            return first
        if first.candidate_answer and first.confidence >= self.consensus_confidence_floor:
            return first
        attempts: list[ModelAnswer] = [first]
        attempts.extend(strategy() for _ in range(repeats - 1))
        buckets: dict[str, dict[str, object]] = defaultdict(
            lambda: {"count": 0, "confidence": 0.0, "answer": None}
        )
        for attempt in attempts:
            key = (attempt.candidate_answer or attempt.answer_text or "").strip()
            buckets[key]["count"] = int(str(buckets[key]["count"])) + 1
            buckets[key]["confidence"] = float(str(buckets[key]["confidence"])) + attempt.confidence
            buckets[key]["answer"] = attempt
        best = sorted(
            buckets.values(),
            key=lambda item: (
                int(str(item["count"])),
                float(str(item["confidence"])),
            ),
            reverse=True,
        )[0]
        return cast(ModelAnswer, best["answer"])


def extract_completion_answer_from_evidence(
    query: QuestionQuery,
    results: tuple[WebSearchResult, ...],
) -> ModelAnswer | None:
    """从网页证据中直接抽取单空填空答案。"""
    normalized_type = (query.question_type or "").strip().lower()
    if normalized_type not in {"completion", "fill", "blank", "填空题", "填空"}:
        return None
    title = query.title or ""
    if "____" not in title and "【1】" not in title:
        return None
    body = cleanup_completion_title(title)
    if "____" in body:
        parts = body.split("____", 1)
    else:
        parts = re.split(r"【\d+】[_＿]*", body, maxsplit=1)
        if len(parts) != 2:
            return None
    prefix, suffix = (part.strip() for part in parts)
    if not prefix and not suffix:
        return None
    candidates: dict[str, dict[str, float | int | str]] = {}
    for index, result in enumerate(results, start=1):
        snippet = " ".join(f"{result.title} {result.snippet}".split())
        answer = match_completion_snippet(prefix, suffix, snippet)
        if not answer:
            continue
        key = normalize_completion_candidate(answer)
        weight = preferred_domain_score(result.url) + max(0.0, 4.0 - (index - 1) * 0.5)
        entry = candidates.setdefault(
            key,
            {
                "answer": answer,
                "score": 0.0,
                "count": 0,
                "first_index": index,
            },
        )
        entry["score"] = float(entry["score"]) + weight
        entry["count"] = int(entry["count"]) + 1
        entry["first_index"] = min(int(entry["first_index"]), index)
    if not candidates:
        return None
    selected = sorted(
        candidates.values(),
        key=lambda item: (
            float(item["score"]),
            int(item["count"]),
            -len(str(item["answer"])),
            -int(item["first_index"]),
        ),
        reverse=True,
    )[0]
    answer = str(selected["answer"])
    return ModelAnswer(
        candidate_answer=answer,
        answer_text=answer,
        explanation=(
            "多条证据命中填空原句，按权威来源与结果顺序加权后抽取得到答案：" f"{answer}。"
        ),
        confidence=0.98,
    )


def cleanup_completion_title(title: str) -> str:
    """去掉填空题前缀与题号占位。"""
    text = re.sub(r"^(单选题|多选题|判断题|填空题)\s*\(\d+(?:\.\d+)?分\)", "", title.strip())
    text = re.sub(r"【\d+】[_＿]*", "____", text)
    text = re.sub(r"[_＿]{2,}", "____", text)
    return " ".join(text.split())


def match_completion_snippet(prefix: str, suffix: str, snippet: str) -> str | None:
    """根据题干前后缀从证据片段中抽取填空答案。"""
    escaped_prefix = re.escape(prefix)
    escaped_suffix = re.escape(suffix)
    answer_pattern = r"([\u4e00-\u9fffA-Za-z0-9《》“”‘’·\-]{1,30})"
    if prefix and suffix:
        pattern = escaped_prefix + answer_pattern + escaped_suffix
    elif prefix:
        pattern = escaped_prefix + answer_pattern
    else:
        pattern = answer_pattern + escaped_suffix
    match = re.search(pattern, snippet)
    if not match:
        return None
    return match.group(1).strip()


def normalize_completion_candidate(value: str) -> str:
    """规整填空候选答案，便于做多证据投票。"""
    return re.sub(r"\s+", "", value or "").strip("《》“”\"'")


def render_search_evidence(results: tuple[WebSearchResult, ...]) -> str:
    """将检索出来的网页结果片段渲染成紧凑的字符串，便于置入 Prompt。

    每个结果将被编号并包含标题、URL 链接及文本摘录（Snippet）。

    参数:
        results: 网页检索结果元组。

    返回:
        str: 供大模型阅读的 RAG 背景参考证据文本。
    """

    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        # 剔除摘录与标题中多余的空白或换行符
        snippet = " ".join(result.snippet.split())
        title = " ".join(result.title.split())
        lines.append(f"[{index}] {title}\nURL: {result.url}\nSnippet: {snippet}")
    return "\n\n".join(lines)
