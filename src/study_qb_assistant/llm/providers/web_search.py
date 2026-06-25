"""用于大模型证据增强回答的可选网络检索提供商。

该模块实现了多种搜索引擎或检索 API（包括 DuckDuckGo 零鉴权检索接口、Google 可编程搜索 API、百度千帆 AI 搜索等）
的适配器，并提供多搜索引擎熔断与容灾组合（Composite）能力，以辅助提高模型题目解答的召回和时效性。
"""

from __future__ import annotations

import os
import re
import time
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from typing import Any

from playwright.sync_api import Playwright, Browser

from ...config import GlobalConfig, get_global_config
from ...models import QuestionQuery
from ...normalization import normalize_text
from ...logger import log_event
from ..search_engines import PlaywrightSearchEngineConfig, resolve_playwright_search_engine
from .web_search_http import (
    get_search_json,
    get_search_text,
    iter_duckduckgo_related,
    post_search_json,
)
from .web_search_types import WebSearchProvider, WebSearchResult


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
            provider_results = rank_search_results(query, provider_results)[:top_k]
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
    proxy_url: str | None = None

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """构建查询请求，向 Google 接口获取搜索结果。"""
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for search_query in build_search_queries(query):
            params = {
                "key": self.api_key,
                "cx": self.cx,
                "q": search_query,
                "num": str(max(1, min(top_k, 10))),
                "hl": "zh-CN",
                "lr": "lang_zh-CN|lang_zh-TW",
                "safe": "active",
            }
            payload = get_search_json(
                self.endpoint,
                params=params,
                proxy_url=self.proxy_url,
            )
            for item in payload.get("items") or ():
                url = str(item.get("link") or "")
                if not url or url in seen:
                    continue
                title = str(item.get("title") or "")
                snippet = str(item.get("snippet") or "")
                if not (title or snippet):
                    continue
                seen.add(url)
                results.append(
                    WebSearchResult(
                        title=title, url=url, snippet=snippet, source=self.provider_name
                    )
                )
                if len(results) >= top_k:
                    return tuple(results)
        return tuple(results)


@dataclass(slots=True)
class BaiduAiSearchProvider:
    """百度千帆 AI 智能搜索 API 适配器。

    使用百度大模型内置的网页检索插件生成精确相关的中文证据。
    """

    api_key: str  # 千帆 API 的 Access Token 或 Bearer 鉴权凭证
    endpoint: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    provider_name: str = "baidu-ai-search"
    proxy_url: str | None = None

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """向百度千帆 AI 搜索端点发送 POST 请求并返回解析后的网页引用。"""
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Appbuilder-Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for search_query in build_search_queries(query, max_chars=72):
            payload = {
                "messages": [{"role": "user", "content": search_query}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": max(1, min(top_k, 50))}],
                "search_filter": {"safe_search": True},
            }
            response = post_search_json(
                self.endpoint,
                payload,
                headers=headers,
                proxy_url=self.proxy_url,
            )
            for item in response.get("references") or ():
                url = str(item.get("url") or "")
                if not url or url in seen:
                    continue
                title = str(item.get("title") or item.get("web_anchor") or "")
                snippet = str(item.get("content") or "")
                if not (title or snippet):
                    continue
                seen.add(url)
                results.append(
                    WebSearchResult(
                        title=title, url=url, snippet=snippet, source=self.provider_name
                    )
                )
                if len(results) >= top_k:
                    return tuple(results)
        return tuple(results)


@dataclass(slots=True)
class DuckDuckGoInstantAnswerProvider:
    """无需 API Key 即可直接使用的 DuckDuckGo 即时回答 API 适配器。"""

    endpoint: str = "https://api.duckduckgo.com/"
    provider_name: str = "duckduckgo-instant-answer"
    proxy_url: str | None = None

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """构建请求，解析 Abstract 或相关 Topics 中的即时参考答案。"""
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for search_query in build_search_queries(query):
            params = {
                "q": search_query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
                "kl": "cn-zh",
            }
            payload = get_search_json(
                self.endpoint,
                params=params,
                proxy_url=self.proxy_url,
            )
            abstract_text = str(payload.get("AbstractText") or "")
            if abstract_text:
                url = str(payload.get("AbstractURL") or "https://duckduckgo.com/")
                if url not in seen:
                    seen.add(url)
                    results.append(
                        WebSearchResult(
                            title=str(payload.get("Heading") or "DuckDuckGo Instant Answer"),
                            url=url,
                            snippet=abstract_text,
                            source=self.provider_name,
                        )
                    )
            for result in iter_duckduckgo_related(payload.get("RelatedTopics") or ()):
                if result.url in seen:
                    continue
                seen.add(result.url)
                results.append(result)
                if len(results) >= top_k:
                    return tuple(results)
        return tuple(results[:top_k])


@dataclass(slots=True)
class BingHtmlSearchProvider:
    """无需 API Key 的 Bing 搜索结果页适配器。"""

    endpoint: str = "https://cn.bing.com/search"
    provider_name: str = "bing-html-search"
    proxy_url: str | None = None

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """抓取 Bing 搜索结果页并提取标题、链接与摘要。"""
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        headers = {"User-Agent": "Mozilla/5.0"}
        for search_query in build_search_queries(query):
            html = get_search_text(
                self.endpoint,
                params={"q": search_query, "setlang": "zh-Hans"},
                headers=headers,
                timeout_seconds=8.0,
                retries=1,
                proxy_url=self.proxy_url,
            )
            for title, url, snippet in iter_bing_html_results(html):
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(
                    WebSearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source=self.provider_name,
                    )
                )
                if len(results) >= top_k:
                    return tuple(results)
        return tuple(results[:top_k])


@dataclass(slots=True)
class BingPlaywrightSearchProvider:
    """基于真实浏览器的页面搜索提供者。

    类名保留 `BingPlaywrightSearchProvider` 是为了兼容既有导入；实际搜索页面
    由 `search_engine` 决定，默认仍为 Bing。
    """

    browser_path: str
    search_engine: str = "bing"
    endpoint: str = ""
    provider_name: str = ""
    proxy_url: str | None = None
    cooldown_seconds: float = 20.0
    page_cache_path: str | None = None
    _playwright_manager: Playwright | Any | None = field(default=None, init=False, repr=False)
    _browser: Browser | Any | None = field(default=None, init=False, repr=False)
    _page_excerpt_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _page_cache_loaded: bool = field(default=False, init=False, repr=False)
    _executor: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """规范化页面搜索引擎配置，并保留旧配置默认行为。"""
        engine = resolve_playwright_search_engine(self.search_engine)
        self.search_engine = engine.key
        if not self.endpoint:
            self.endpoint = engine.endpoint
        if not self.provider_name:
            self.provider_name = f"{engine.key}-playwright-search"

    def search(self, query: QuestionQuery, *, top_k: int = 5) -> tuple[WebSearchResult, ...]:
        """使用独立线程承载 Playwright 浏览器搜索，避免与服务事件循环冲突。"""
        future = self._ensure_executor().submit(self._search_sync, query, top_k)
        return future.result()

    def _search_sync(
        self, query: QuestionQuery, top_k: int = 5
    ) -> tuple[WebSearchResult, ...]:
        """在专用线程里执行同步 Playwright 搜索。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("playwright not installed") from exc

        self._ensure_browser(sync_playwright)
        assert self._browser is not None
        engine = resolve_playwright_search_engine(self.search_engine)
        last_error: Exception | None = None
        for attempt in range(2):
            page = None
            try:
                results: list[WebSearchResult] = []
                seen_urls: set[str] = set()
                page = self._browser.new_page()
                for search_query in build_search_queries(query):
                    try:
                        page.goto(
                            build_playwright_search_url(
                                engine, search_query, endpoint=self.endpoint
                            ),
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        try:
                            page.locator(engine.wait_selector).first.wait_for(timeout=8000)
                        except Exception:
                            page.wait_for_timeout(1000)
                        items = page.locator(engine.result_selector)
                        count = min(items.count(), max(top_k * 3, top_k))
                        for index in range(count):
                            item = items.nth(index)
                            title = first_playwright_locator_text(item, engine.title_selectors)
                            url = first_playwright_locator_attribute(
                                item,
                                engine.link_selector,
                                "href",
                            )
                            snippet = first_playwright_locator_text(
                                item,
                                engine.snippet_selectors,
                                allow_item_fallback=False,
                            )
                            normalized_url = resolve_playwright_result_url(
                                url,
                                engine_key=engine.key,
                                endpoint=self.endpoint,
                            )
                            if title and normalized_url and normalized_url not in seen_urls:
                                seen_urls.add(normalized_url)
                                results.append(
                                    WebSearchResult(
                                        title=clean_search_html_text(title),
                                        url=normalized_url,
                                        snippet=clean_search_html_text(snippet),
                                        source=self.provider_name,
                                    )
                                )
                            if len(results) >= top_k * 3:
                                break
                        if len(results) >= top_k * 3:
                            break
                    except Exception:
                        continue
                ranked = tuple(rank_search_results(query, tuple(results))[:top_k])
                return self._enrich_results_with_page_excerpt(query, ranked)
            except Exception as exc:
                last_error = exc
                self._reset_browser()
                self._ensure_browser(sync_playwright)
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
        raise RuntimeError(str(last_error) if last_error else "playwright search failed")

    def _ensure_executor(self) -> ThreadPoolExecutor:
        """保证 Playwright 搜索始终在同一个专用线程中运行。"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"playwright-search-{self.search_engine}",
            )
        return self._executor

    def _enrich_results_with_page_excerpt(
        self,
        query: QuestionQuery,
        results: tuple[WebSearchResult, ...],
    ) -> tuple[WebSearchResult, ...]:
        """对填空题结果补充正文级摘要，降低摘要误导。"""
        normalized_type = (query.question_type or "").strip().lower()
        if normalized_type not in {"completion", "fill", "blank", "填空题", "填空"}:
            return results
        page = None
        enriched: list[WebSearchResult] = []
        try:
            assert self._browser is not None
            page = self._browser.new_page()
            for index, result in enumerate(results, start=1):
                if index > 5:
                    enriched.append(result)
                    continue
                if completion_excerpt_has_signal(query, result.snippet):
                    enriched.append(result)
                    continue
                excerpt = self._page_excerpt_cache.get(result.url)
                if excerpt is None:
                    excerpt = extract_page_excerpt(page, result.url, query)
                    if excerpt:
                        self._page_excerpt_cache[result.url] = excerpt
                        try:
                            self._save_page_excerpt_cache()
                        except Exception:
                            pass
                enriched.append(
                    WebSearchResult(
                        title=result.title,
                        url=result.url,
                        snippet=excerpt or result.snippet,
                        source=result.source,
                    )
                )
        except Exception:
            return results
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
        return tuple(rank_search_results(query, tuple(enriched))[: len(results)])

    def _ensure_browser(self, sync_playwright) -> None:
        """确保浏览器实例可复用。"""
        if self._browser is not None:
            return
        self._load_page_excerpt_cache()
        self._playwright_manager = sync_playwright().start()
        launch_options: dict[str, Any] = {
            "executable_path": self.browser_path,
            "headless": True,
        }
        if self.proxy_url:
            launch_options["proxy"] = {"server": self.proxy_url}
        self._browser = self._playwright_manager.chromium.launch(**launch_options)

    def _reset_browser(self) -> None:
        """重置失效的浏览器实例。"""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        self._browser = None
        if self._playwright_manager is not None:
            try:
                self._playwright_manager.stop()
            except Exception:
                pass
        self._playwright_manager = None

    def _load_page_excerpt_cache(self) -> None:
        """加载页面摘录缓存。"""
        if self._page_cache_loaded:
            return
        self._page_cache_loaded = True
        if not self.page_cache_path:
            return
        path = Path(self.page_cache_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._page_excerpt_cache = {
                str(key): str(value) for key, value in payload.items() if str(value).strip()
            }

    def _save_page_excerpt_cache(self) -> None:
        """保存页面摘录缓存。"""
        if not self.page_cache_path:
            return
        path = Path(self.page_cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._page_excerpt_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_search_provider(
    runtime_config: dict[str, object] | None = None,
    *,
    global_config: GlobalConfig | None = None,
) -> WebSearchProvider | None:
    """根据运行时配置和部署级配置构建搜索引擎提供者实例。"""
    config = global_config or get_global_config()
    runtime = runtime_config or {}

    proxy_url = str(runtime.get("search_proxy") or config.search_proxy).strip() or None

    # 尝试从新版 web_search_configs 中加载
    import json

    web_search_configs_str = str(runtime.get("web_search_configs") or "").strip()
    configs = []
    if web_search_configs_str:
        try:
            configs = json.loads(web_search_configs_str)
        except Exception:
            configs = []

    providers: list[WebSearchProvider] = []

    if configs and isinstance(configs, list):
        for item in configs:
            if not isinstance(item, dict) or item.get("status") != "active":
                continue

            item_provider = str(item.get("provider") or "").strip().lower()
            item_proxy_url = str(item.get("proxy_url") or "").strip() or proxy_url

            if item_provider in {"duckduckgo", "ddg", "keyless", "free"}:
                providers.append(DuckDuckGoInstantAnswerProvider(proxy_url=item_proxy_url))
                providers.append(BingHtmlSearchProvider(proxy_url=item_proxy_url))
            elif item_provider == "google":
                api_key = str(item.get("api_key") or "").strip()
                cx = str(item.get("cx") or "").strip()
                if api_key and cx:
                    providers.append(
                        GoogleCustomSearchProvider(
                            api_key=api_key,
                            cx=cx,
                            proxy_url=item_proxy_url,
                        )
                    )
            elif item_provider == "baidu":
                api_key = str(item.get("api_key") or "").strip()
                if api_key:
                    providers.append(
                        BaiduAiSearchProvider(
                            api_key=api_key,
                            proxy_url=item_proxy_url,
                        )
                    )
            elif item_provider == "playwright":
                bing_browser_path = resolve_browser_path()
                if bing_browser_path:
                    providers.append(
                        BingPlaywrightSearchProvider(
                            browser_path=bing_browser_path,
                            search_engine=str(
                                item.get("search_engine") or item.get("engine") or "bing"
                            ),
                            proxy_url=item_proxy_url,
                            page_cache_path=(
                                str(config.search_page_cache_path_resolved)
                                if config.search_page_cache_path_resolved is not None
                                else None
                            ),
                        )
                    )

    # 如果没有找到任何有效的 custom configs，则 fallback 使用旧版 web_search_provider
    if not providers:
        raw_provider = str(runtime.get("web_search_provider") or config.web_search_provider).strip()
        if raw_provider.lower() in {"0", "false", "no", "none", "off", "disabled"}:
            return None

        requested = [
            part.strip().lower()
            for part in (raw_provider or "duckduckgo").split(",")
            if part.strip()
        ]

        browser_provider: WebSearchProvider | None = None
        bing_browser_path = resolve_browser_path()
        if "playwright" in requested and bing_browser_path:
            browser_provider = BingPlaywrightSearchProvider(
                browser_path=bing_browser_path,
                proxy_url=proxy_url,
                page_cache_path=(
                    str(config.search_page_cache_path_resolved)
                    if config.search_page_cache_path_resolved is not None
                    else None
                ),
            )
        # 允许指定并添加多个搜索引擎
        wants_keyless = any(name in requested for name in ("duckduckgo", "ddg", "keyless", "free"))
        if wants_keyless:
            providers.append(DuckDuckGoInstantAnswerProvider(proxy_url=proxy_url))
            providers.append(BingHtmlSearchProvider(proxy_url=proxy_url))
        if "google" in requested:
            google_key = str(
                runtime.get("google_search_api_key") or config.google_search_api_key
            ).strip()
            google_cx = str(runtime.get("google_search_cx") or config.google_search_cx).strip()
            if google_key and google_cx:
                providers.append(
                    GoogleCustomSearchProvider(
                        api_key=google_key,
                        cx=google_cx,
                        proxy_url=proxy_url,
                    )
                )
        if "baidu" in requested:
            baidu_key = str(
                runtime.get("baidu_search_api_key") or config.baidu_search_api_key
            ).strip()
            if baidu_key:
                providers.append(BaiduAiSearchProvider(api_key=baidu_key, proxy_url=proxy_url))
        if browser_provider is not None:
            providers.append(browser_provider)

    if not providers:
        return None
    return CompositeWebSearchProvider(tuple(providers))


def build_search_provider_from_env() -> WebSearchProvider | None:
    """根据全局环境配置动态构建搜索提供者。"""
    return build_search_provider()


def build_search_query(query: QuestionQuery, *, max_chars: int = 160) -> str:
    """从 OCS 原始输入题目中清洗、提炼出适于搜索引擎查询的精简关键词。

    会自动去除诸如 “单选题”、“多选题” 等干扰项以及选项占位符，限制长度并拼接选项。

    参数:
        query: 题目查询。
        max_chars: 搜索查询词的最大字符数限制，默认 160。

    返回:
        str: 净化后的搜索关键词字符串。
    """

    title = search_ready_title(query.title)
    if len(title) >= max_chars:
        return title[:max_chars]

    # 若字数未达上限，则将前几个选项的文本作为辅助检索信息一并拼接，以便召回正确选项
    remaining = max_chars - len(title)
    option_text = " ".join(
        strip_search_option_label(option) for option in query.options[:4] if len(option) <= 40
    )
    if option_text and remaining > 12:
        return f"{title} {option_text[:remaining - 1]}".strip()
    return title


def build_search_queries(query: QuestionQuery, *, max_chars: int = 160) -> tuple[str, ...]:
    """为同一道题生成多个检索查询变体，提高召回率。"""
    base = build_search_query(query, max_chars=max_chars)
    variants: list[str] = [base]
    plain_title = search_ready_title(query.title)
    if plain_title and plain_title != base:
        variants.append(plain_title[:max_chars])
        if len(plain_title) <= 48:
            variants.append(f'"{plain_title}"'[:max_chars])
    if query.options:
        option_text = " ".join(strip_search_option_label(option) for option in query.options[:4])
        expanded = f"{plain_title or base} {option_text}".strip()
        if expanded:
            variants.append(expanded[:max_chars])
    compact = re.sub(r"[（）()【】\\[\\]，。；：、“”‘’\"'·,.;:!?？!]", " ", plain_title or base)
    compact = " ".join(compact.split())
    if compact:
        variants.append(compact[:max_chars])
        if len(compact) <= 48:
            variants.append(f'"{compact}"'[:max_chars])
    normalized_type = (query.question_type or "").strip().lower()
    if normalized_type in {"completion", "multiple", "judgement"}:
        anchor = plain_title or base
        if len(anchor) <= 64:
            for domain in ("gov.cn", "12371.cn", "people.com.cn"):
                variants.append(f'"{anchor}" site:{domain}'[:max_chars].strip())
    if normalized_type in {"completion", "fill", "blank", "填空题", "填空"}:
        completion_body = completion_search_body(query.title)
        if "____" in completion_body:
            prefix, suffix = (part.strip() for part in completion_body.split("____", 1))
            if prefix:
                prefix_short = prefix[:40]
                variants.append(f'"{prefix_short}"')
            if suffix:
                suffix_short = suffix[:40]
                variants.append(f'"{suffix_short}"')
                for domain in ("gov.cn", "12371.cn", "people.com.cn"):
                    variants.append(f'"{suffix_short}" site:{domain}')
            if prefix and suffix:
                combo = f"{prefix} {suffix}".strip()[:48]
                variants.append(f'"{combo}"')
    if len((plain_title or base).strip()) <= 28 and query.options:
        for option in query.options[:4]:
            option_text = strip_search_option_label(option)
            if not option_text:
                continue
            variants.append(f"{plain_title or base} {option_text}"[:max_chars].strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return tuple(deduped)


def normalize_search_text(title: str) -> str:
    """去除题型前缀和填空占位符，得到更稳定的搜索文本。"""
    text = title or ""
    text = re.sub(r"^[一二三四五六七八九十]+[\.．、]\s*", "", text)
    text = re.sub(r"^(单选题|多选题|判断题|填空题)\s*\(\d+(?:\.\d+)?分\)", "", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"【\d+】[_＿]+", " ", text)
    text = re.sub(r"【】[_＿]+", " ", text)
    text = re.sub(r"[_＿]{2,}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def search_ready_title(title: str) -> str:
    """把题干清洗成更适合搜索引擎的关键词序列。"""
    normalized = normalize_search_text(title)
    parts = [
        part.strip()
        for part in re.split(r"[，。；：、“”‘’\"'！？?!（）()【】\[\]\s]+", normalized)
        if part.strip()
    ]
    informative = [part for part in parts if len(part) > 1 or any(char.isdigit() for char in part)]
    if informative:
        return " ".join(informative)
    return normalized


def completion_search_body(title: str) -> str:
    """提取填空题去前缀后的原句骨架。"""
    text = normalize_search_text(title)
    text = text.replace("【1】", "____").replace("【2】", "____")
    text = re.sub(r"[_＿]{2,}", "____", text)
    return " ".join(text.split())


def strip_search_option_label(option: str) -> str:
    """去掉搜索查询里选项文本的字母前缀。"""
    return re.sub(r"^\s*[A-Fa-f][\.、．:：]\s*", "", option).strip()


def iter_bing_html_results(html: str) -> tuple[tuple[str, str, str], ...]:
    """从 Bing 搜索结果页 HTML 中提取结果条目。"""
    blocks = re.findall(r'(<li class="b_algo".*?</li>)', html, flags=re.S)
    results: list[tuple[str, str, str]] = []
    for block in blocks:
        match = re.search(
            r'<h2[^>]*>\s*<a[^>]*href="(.*?)"[^>]*>(.*?)</a>\s*</h2>',
            block,
            flags=re.S,
        )
        if not match:
            continue
        url, raw_title = match.groups()
        snippet_match = re.search(r"<p>(.*?)</p>", block, flags=re.S)
        title = clean_search_html_text(raw_title)
        snippet = clean_search_html_text(snippet_match.group(1)) if snippet_match else ""
        cleaned_url = url.replace("&amp;", "&").strip()
        if title and cleaned_url:
            results.append((title, cleaned_url, snippet))
    return tuple(results)


def clean_search_html_text(value: str) -> str:
    """清洗搜索结果 HTML 片段中的标签和空白。"""
    text = re.sub(r"<.*?>", " ", value or "")
    text = unescape(text).replace("&nbsp;", " ")
    return " ".join(text.split()).strip()


def build_playwright_search_url(
    engine: PlaywrightSearchEngineConfig,
    search_query: str,
    *,
    endpoint: str | None = None,
) -> str:
    """按页面搜索引擎配置生成 Playwright 要打开的搜索结果页地址。"""
    params = {key: value for key, value in engine.static_params}
    params[engine.query_param] = search_query
    target = endpoint or engine.endpoint
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{urlencode(params)}"


def first_playwright_locator_text(
    locator: Any,
    selectors: tuple[str, ...],
    *,
    allow_item_fallback: bool = True,
) -> str:
    """从 Playwright locator 中按多个候选选择器提取第一段可用文本。"""
    for selector in selectors:
        try:
            parts = [part.strip() for part in locator.locator(selector).all_inner_texts()]
        except Exception:
            continue
        text = " ".join(part for part in parts if part)
        if text:
            return text
    if not allow_item_fallback:
        return ""
    try:
        return " ".join(str(locator.inner_text(timeout=1000) or "").split())
    except Exception:
        return ""


def first_playwright_locator_attribute(locator: Any, selector: str, attribute: str) -> str:
    """从 Playwright locator 的第一个匹配元素读取属性。"""
    try:
        return str(locator.locator(selector).first.get_attribute(attribute) or "").strip()
    except Exception:
        return ""


def resolve_playwright_result_url(url: str, *, engine_key: str, endpoint: str) -> str:
    """解析不同搜索页面的跳转链接，尽量还原真实结果 URL。"""
    normalized_url = (url or "").replace("&amp;", "&").strip()
    if not normalized_url:
        return ""
    if normalized_url.startswith("/"):
        normalized_url = urljoin(endpoint, normalized_url)
    if engine_key == "bing":
        return resolve_bing_redirect_url(normalized_url)
    if engine_key == "google":
        return resolve_google_redirect_url(normalized_url)
    if engine_key == "baidu":
        return resolve_baidu_redirect_url(normalized_url)
    if engine_key == "duckduckgo":
        return resolve_duckduckgo_redirect_url(normalized_url)
    return normalized_url


def rank_search_results(
    query: QuestionQuery,
    results: tuple[WebSearchResult, ...],
) -> tuple[WebSearchResult, ...]:
    """按题干关键词和选项重合度对搜索结果进行本地重排与过滤。"""
    scored: list[tuple[float, WebSearchResult]] = []
    query_keywords = extract_query_keywords(query)
    option_keywords = {
        normalize_text(strip_search_option_label(option))
        for option in query.options
        if option.strip()
    }
    option_keywords = {item for item in option_keywords if len(item) >= 2}
    for result in results:
        haystack = normalize_text(f"{result.title} {result.snippet}")
        if not haystack:
            continue
        keyword_hits = sum(1 for keyword in query_keywords if keyword in haystack)
        option_hits = sum(1 for option in option_keywords if option in haystack)
        score = keyword_hits + (option_hits * 0.8) + preferred_domain_score(result.url)
        if score <= 0:
            continue
        scored.append((score, result))
    scored.sort(key=lambda item: item[0], reverse=True)
    return tuple(result for _score, result in scored)


def extract_query_keywords(query: QuestionQuery) -> tuple[str, ...]:
    """从题干中提取适合搜索重排的关键词。"""
    parts = [
        normalize_text(part)
        for part in re.split(
            r"[，。；：、“”‘’\"'！？?!（）()【】\[\]\s]+", search_ready_title(query.title)
        )
        if part.strip()
    ]
    return tuple(part for part in parts if len(part) >= 2)


def preferred_domain_score(url: str) -> float:
    """为更权威、更接近课程资料的域名增加重排分值。"""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if any(domain in host for domain in ("gov.cn", "npc.gov.cn", "moj.gov.cn")):
        return 2.4
    if any(
        domain in host
        for domain in ("people.com.cn", "12371.cn", "qstheory.cn", "cctv.com", "cctv.cn")
    ):
        return 2.0
    if any(domain in host for domain in ("xuexi.cn", "news.cn", "china.com.cn", "cppcc.gov.cn")):
        return 1.8
    if host.endswith(".edu.cn"):
        return 1.4
    if host.endswith(".gov") or ".gov." in host:
        return 1.2
    return 0.0


def resolve_browser_path() -> str | None:
    """解析可用于 Playwright 的本地浏览器路径。"""
    config = get_global_config()
    configured_raw = config.search_browser_path.strip()
    if configured_raw and os.path.exists(configured_raw):
        return configured_raw
    candidates: list[Path] = []
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ]
    )
    for candidate in candidates:
        if os.path.exists(str(candidate)):
            return str(candidate)
    return None


def resolve_bing_redirect_url(url: str) -> str:
    """把 Bing 跳转链接中的真实目标地址解出来。"""
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    candidate = query.get("u")
    if candidate:
        value = candidate[0]
        if value.startswith("a1"):
            try:
                import base64

                padding = "=" * ((4 - len(value[2:]) % 4) % 4)
                decoded = base64.b64decode(value[2:] + padding).decode("utf-8", errors="ignore")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                return url
    return url


def resolve_google_redirect_url(url: str) -> str:
    """把 Google `/url?q=...` 跳转链接还原为目标地址。"""
    parsed = urlparse(url)
    if "google." not in parsed.netloc or parsed.path != "/url":
        return url
    query = parse_qs(parsed.query)
    for key in ("q", "url"):
        candidate = query.get(key)
        if candidate and candidate[0].startswith("http"):
            return candidate[0]
    return url


def resolve_baidu_redirect_url(url: str) -> str:
    """把百度结果页的 `link?url=...` 形式跳转地址还原为可读 URL。"""
    parsed = urlparse(url)
    if "baidu.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    for key in ("url", "wd"):
        candidate = query.get(key)
        if candidate and candidate[0].startswith("http"):
            return candidate[0]
    return url


def resolve_duckduckgo_redirect_url(url: str) -> str:
    """把 DuckDuckGo HTML 页面跳转链接还原为目标地址。"""
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    candidate = query.get("uddg") or query.get("u")
    if candidate and candidate[0].startswith("http"):
        return candidate[0]
    return url


def cleanup_completion_title(title: str) -> str:
    """清理填空题题型前缀，并把各种空位标记统一成 `____`。"""
    text = re.sub(r"^(单选题|多选题|判断题|填空题)\s*\(\d+(?:\.\d+)?分\)", "", title.strip())
    text = re.sub(r"【\d+】[_＿]*", "____", text)
    text = re.sub(r"[_＿]{2,}", "____", text)
    return text.strip()


def completion_excerpt_has_signal(query: QuestionQuery, snippet: str) -> bool:
    """判断摘要是否已经足够像填空原句。"""
    body = cleanup_completion_title(query.title)
    if "____" not in body:
        return False
    prefix, suffix = (part.strip() for part in body.split("____", 1))
    compact = normalize_text(snippet)
    return bool(
        prefix
        and normalize_text(prefix) in compact
        and suffix
        and normalize_text(suffix) in compact
    )


def extract_page_excerpt(page: Any, url: str, query: QuestionQuery) -> str:
    """打开结果页正文并抽取与题干最相关的句子。"""
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1200)
    body_text = page.locator("body").inner_text(timeout=5000)
    return select_relevant_excerpt(query, body_text)


def select_relevant_excerpt(query: QuestionQuery, body_text: str) -> str:
    """从正文中挑选最接近题干的句子。"""
    compact = " ".join((body_text or "").split())
    if not compact:
        return ""
    completion_sentence = extract_completion_sentence(query, compact)
    if completion_sentence:
        return completion_sentence[:400]
    sentences = re.split(r"(?<=[。！？!?；;])", compact)
    keywords = extract_query_keywords(query)
    best_sentence = ""
    best_score = -1.0
    for sentence in sentences:
        normalized_sentence = normalize_text(sentence)
        if not normalized_sentence:
            continue
        keyword_hits = sum(1 for keyword in keywords if keyword in normalized_sentence)
        score = float(keyword_hits)
        if score > best_score:
            best_score = score
            best_sentence = sentence.strip()
    return best_sentence[:400]


def extract_completion_sentence(query: QuestionQuery, text: str) -> str:
    """若正文中直接出现填空原句，优先返回命中句子。"""
    normalized_type = (query.question_type or "").strip().lower()
    if normalized_type not in {"completion", "fill", "blank", "填空题", "填空"}:
        return ""
    body = cleanup_completion_title(query.title)
    if "____" not in body:
        return ""
    prefix, suffix = (part.strip() for part in body.split("____", 1))
    pattern = build_completion_pattern(prefix, suffix)
    match = re.search(pattern, text)
    if not match:
        return ""
    start = max(0, text.rfind("。", 0, match.start()))
    end_candidates = [text.find(mark, match.end()) for mark in "。！？!?；;"]
    end_candidates = [value for value in end_candidates if value >= 0]
    end = min(end_candidates) + 1 if end_candidates else min(len(text), match.end() + 120)
    sentence = text[start:end].strip("。！？!?；; \t")
    return sentence


def build_completion_pattern(prefix: str, suffix: str) -> str:
    """构建填空题正文抽取的匹配模式。"""
    answer_pattern = r"([\u4e00-\u9fffA-Za-z0-9《》“”‘’·\-]{1,30})"
    escaped_prefix = re.escape(prefix)
    escaped_suffix = re.escape(suffix)
    if prefix and suffix:
        return escaped_prefix + answer_pattern + escaped_suffix
    if prefix:
        return escaped_prefix + answer_pattern
    return answer_pattern + escaped_suffix
