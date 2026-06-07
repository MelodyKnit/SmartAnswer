"""用于大模型证据增强回答的可选网络检索提供商。

该模块实现了多种搜索引擎或检索 API（包括 DuckDuckGo 零鉴权检索接口、Google 可编程搜索 API、百度千帆 AI 搜索等）
的适配器，并提供多搜索引擎熔断与容灾组合（Composite）能力，以辅助提高模型题目解答的召回和时效性。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..http_client import HttpClientError, get_json, post_json
from ..models import QuestionQuery
from ..runtime_log import log_event


@dataclass(slots=True)
class WebSearchResult:
    """标准化后的网页检索结果片段结构体。"""

    title: str  # 网页标题
    url: str  # 网页 URL 链接
    snippet: str  # 文本摘要/内容摘录
    source: str  # 数据源/搜索引擎标识 (例如 "google-custom-search")


class WebSearchProvider(Protocol):
    """搜索引擎提供商的极简协议接口。

    所有具体的搜索引擎适配类都需要实现此协议以保证接口一致性。
    """

    provider_name: str

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """为给定的题目查询执行实时搜索，并返回清洗后的网页摘要片段列表。

        参数:
            query: 题目查询结构体 (QuestionQuery)。
            top_k: 返回的最大结果数量，默认为 5。

        返回:
            tuple[WebSearchResult, ...]: 标准化网页搜索结果元组。
        """


@dataclass(slots=True)
class CompositeWebSearchProvider:
    """组合式搜索引擎提供商。

    它负责按顺序调用内部的多个搜索引擎适配器，合并检索结果，去重 URL，
    并在某个引擎接口报错时对其施加熔断冷却（cooldown），从而提升检索的高可用性。
    """

    providers: tuple[WebSearchProvider, ...]  # 包含的所有底层搜索引擎元组
    provider_name: str = "web-search"  # 提供商组合名称
    cooldown_seconds: float = 120.0  # 接口出错时的冷却惩罚时间（秒）
    _disabled_until: dict[str, float] = field(default_factory=dict)  # 记录各引擎被熔断恢复的时间戳

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """按顺序调用各个可用的搜索引擎，合并去重后返回前 top_k 个结果。

        若某个引擎处于冷却期则跳过；若调用抛出异常则自动触发熔断。

        参数:
            query: 题目查询结构体。
            top_k: 需要获取的结果总数限制。

        返回:
            tuple[WebSearchResult, ...]: 合并去重后的检索结果元组。
        """
        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        for provider in self.providers:
            disabled_until = self._disabled_until.get(provider.provider_name, 0.0)
            # 判断是否仍处于熔断冷却期
            if disabled_until > time.time():
                log_event(
                    "web_search_skipped",
                    {
                        "provider": provider.provider_name,
                        "title": query.title,
                        "reason": "cooldown_after_error",
                        "remaining_seconds": round(disabled_until - time.time(), 2),
                    },
                )
                continue
            try:
                provider_results = provider.search(query, top_k=top_k)
            except Exception as exc:
                # 调用出错，对该提供商施加 cooldown 惩罚，防止影响后续的并发请求
                self._disabled_until[provider.provider_name] = time.time() + self.cooldown_seconds
                log_event(
                    "web_search_error",
                    {
                        "provider": provider.provider_name,
                        "title": query.title,
                        "error": str(exc),
                        "cooldown_seconds": self.cooldown_seconds,
                    },
                )
                continue
            # 合并并去重 URL
            for result in provider_results:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                # 收集满 top_k 个结果即提前返回
                if len(results) >= top_k:
                    return tuple(results)
        return tuple(results)


@dataclass(slots=True)
class GoogleCustomSearchProvider:
    """Google 可编程搜索引擎服务适配器。

    使用 Google Custom Search JSON API 检索网页。
    """

    api_key: str  # Google API 密钥
    cx: str  # 搜索引擎的唯一标识符 CX ID
    endpoint: str = "https://www.googleapis.com/customsearch/v1"
    provider_name: str = "google-custom-search"

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """构建查询请求，向 Google 接口获取搜索结果。"""
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": build_search_query(query),
            "num": str(max(1, min(top_k, 10))),
            "hl": "zh-CN",
            "lr": "lang_zh-CN|lang_zh-TW",
            "safe": "active",
        }
        payload = _get_json(self.endpoint, params=params)
        return tuple(
            WebSearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("link") or ""),
                snippet=str(item.get("snippet") or ""),
                source=self.provider_name,
            )
            for item in payload.get("items") or ()
            if item.get("link") and (item.get("title") or item.get("snippet"))
        )


@dataclass(slots=True)
class BaiduAiSearchProvider:
    """百度千帆 AI 智能搜索 API 适配器。

    使用百度大模型内置的网页检索插件生成精确相关的中文证据。
    """

    api_key: str  # 千帆 API 的 Access Token 或 Bearer 鉴权凭证
    endpoint: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    provider_name: str = "baidu-ai-search"

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """向百度千帆 AI 搜索端点发送 POST 请求并返回解析后的网页引用。"""
        # 构建精炼的中文搜索查询词（限制在 72 字符内）
        search_query = build_search_query(query, max_chars=72)
        payload = {
            "messages": [{"role": "user", "content": search_query}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": max(1, min(top_k, 50))}],
            "search_filter": {"safe_search": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Appbuilder-Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = _post_json(self.endpoint, payload, headers=headers)
        references = response.get("references") or []
        return tuple(
            WebSearchResult(
                title=str(item.get("title") or item.get("web_anchor") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
                source=self.provider_name,
            )
            for item in references
            if item.get("url") and (item.get("title") or item.get("content"))
        )


@dataclass(slots=True)
class DuckDuckGoInstantAnswerProvider:
    """无需 API Key 即可直接使用的 DuckDuckGo 即时回答 API 适配器。"""

    endpoint: str = "https://api.duckduckgo.com/"
    provider_name: str = "duckduckgo-instant-answer"

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """构建请求，解析 Abstract 或相关 Topics 中的即时参考答案。"""
        params = {
            "q": build_search_query(query),
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
            "kl": "cn-zh",
        }
        payload = _get_json(self.endpoint, params=params)
        results: list[WebSearchResult] = []
        abstract_text = str(payload.get("AbstractText") or "")
        # 如果返回了概括性的简介文本，则将其作为置信度最高的首条证据
        if abstract_text:
            results.append(
                WebSearchResult(
                    title=str(payload.get("Heading") or "DuckDuckGo Instant Answer"),
                    url=str(payload.get("AbstractURL") or "https://duckduckgo.com/"),
                    snippet=abstract_text,
                    source=self.provider_name,
                )
            )
        # 遍历相关关联话题 Topic 以丰富证据池
        for result in _iter_duckduckgo_related(payload.get("RelatedTopics") or ()):
            results.append(result)
            if len(results) >= top_k:
                break
        return tuple(results[:top_k])


def build_search_provider_from_env() -> WebSearchProvider | None:
    """根据环境变量配置动态构建并返回搜索引擎提供者实例。

    当环境变量 STQB_WEB_SEARCH_PROVIDER 被设为 "disabled" 或 "none" 时，禁用搜索并返回 None。

    返回:
        WebSearchProvider | None: 构建的搜索引擎（如果是多引擎，返回组合式提供商）或 None。
    """

    raw_provider = os.getenv("STQB_WEB_SEARCH_PROVIDER", "").strip()
    if raw_provider.lower() in {"0", "false", "no", "none", "off", "disabled"}:
        return None

    requested = [
        part.strip().lower()
        for part in (raw_provider or "duckduckgo").split(",")
        if part.strip()
    ]

    providers: list[WebSearchProvider] = []
    # 允许指定并添加多个搜索引擎
    if any(name in requested for name in ("duckduckgo", "ddg", "keyless", "free")):
        providers.append(DuckDuckGoInstantAnswerProvider())
    if "google" in requested:
        google_key = os.getenv("STQB_GOOGLE_SEARCH_API_KEY")
        google_cx = os.getenv("STQB_GOOGLE_SEARCH_CX")
        if google_key and google_cx:
            providers.append(GoogleCustomSearchProvider(api_key=google_key, cx=google_cx))
    if "baidu" in requested:
        baidu_key = os.getenv("STQB_BAIDU_SEARCH_API_KEY")
        if baidu_key:
            providers.append(BaiduAiSearchProvider(api_key=baidu_key))

    if not providers:
        return None
    return CompositeWebSearchProvider(tuple(providers))


def build_search_query(query: QuestionQuery, *, max_chars: int = 160) -> str:
    """从 OCS 原始输入题目中清洗、提炼出适于搜索引擎查询的精简关键词。

    会自动去除诸如 “单选题”、“多选题” 等干扰项以及选项占位符，限制长度并拼接选项。

    参数:
        query: 题目查询。
        max_chars: 搜索查询词的最大字符数限制，默认 160。

    返回:
        str: 净化后的搜索关键词字符串。
    """

    title = query.title
    # 清洗题目题型前缀
    title = title.replace("单选题(1分)", "")
    title = title.replace("多选题(1分)", "")
    title = title.replace("判断题(1分)", "")
    title = title.replace("填空题(1分)", "")
    title = title.replace("【1】____", "")
    title = title.replace("____", "")
    title = " ".join(title.split())  # 去除冗余空白
    if len(title) >= max_chars:
        return title[:max_chars]

    # 若字数未达上限，则将前几个选项的文本作为辅助检索信息一并拼接，以便召回正确选项
    remaining = max_chars - len(title)
    option_text = " ".join(option for option in query.options[:4] if len(option) <= 40)
    if option_text and remaining > 12:
        return f"{title} {option_text[:remaining - 1]}".strip()
    return title


def _get_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    timeout_seconds: float = 2.0,
) -> dict:
    """发送 GET 请求并解析 JSON，支持代理设置。"""
    try:
        return get_json(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
            proxy_env="STQB_SEARCH_PROXY",
        )
    except (HttpClientError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"search request failed: {exc}") from exc


def _post_json(url: str, payload: dict, *, headers: dict[str, str]) -> dict:
    """发送 POST 请求并解析 JSON，支持代理设置。"""
    try:
        return post_json(
            url,
            payload,
            headers=headers,
            timeout=12,
            proxy_env="STQB_SEARCH_PROXY",
        )
    except (HttpClientError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"search request failed: {exc}") from exc


def _iter_duckduckgo_related(items: object) -> tuple[WebSearchResult, ...]:
    """递归遍历 DuckDuckGo 返回的 Topics 列表，转换为 standard WebSearchResult 对象。"""
    results: list[WebSearchResult] = []
    if not isinstance(items, list):
        return ()
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("Topics")
        # 如果是嵌套的分组主题，递归遍历
        if isinstance(nested, list):
            results.extend(_iter_duckduckgo_related(nested))
            continue
        text = str(item.get("Text") or "")
        url = str(item.get("FirstURL") or "")
        if not text or not url:
            continue
        # 尝试通过 " - " 拆分，取得首段作为关联主题的标题
        title = text.split(" - ", 1)[0].strip() or "DuckDuckGo related topic"
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=text,
                source="duckduckgo-instant-answer",
            )
        )
    return tuple(results)
