"""基于网络检索证据增强大模型解答（RAG）的装饰器。

该模块实现了一个包装器类，它将网络搜索引擎（SearchProvider）与大模型生成器（ModelProvider）相结合。
通过在调用模型回答前先从网络中检索相关信息，并将这些检索结果拼接在 Prompt 中作为证据，提升模型作答的准确率与时效性。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ModelAnswer, QuestionQuery
from ..runtime_log import log_event
from .base import ModelProvider
from .web_search import WebSearchProvider, WebSearchResult


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

        # 1. 调用搜索引擎执行网络搜索
        results = self.search_provider.search(query, top_k=self.top_k)
        log_event(
            "web_search_results",
            {
                "provider": self.search_provider.provider_name,
                "title": query.title,
                "result_count": len(results),
                "results": [
                    {
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet[:220],
                        "source": result.source,
                    }
                    for result in results[: self.top_k]
                ],
            },
        )
        # 2. 检查底层大模型提供商是否支持接收检索证据进行推理
        answer_with_evidence = getattr(self.model_provider, "answer_with_evidence", None)
        if answer_with_evidence is None or not callable(answer_with_evidence) or not results:
            # 不支持或未搜索到结果时，后退为常规生成
            return self.model_provider.answer(query)
        # 支持时，将检索结果元组作为证据传递进去
        return answer_with_evidence(query, results)


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
