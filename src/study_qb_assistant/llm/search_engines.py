"""联网搜索引擎配置的轻量共享定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaywrightSearchEngineConfig:
    """Playwright 浏览器搜索页面配置。"""

    key: str
    display_name: str
    endpoint: str
    query_param: str
    result_selector: str
    link_selector: str
    title_selectors: tuple[str, ...]
    snippet_selectors: tuple[str, ...]
    wait_selector: str
    static_params: tuple[tuple[str, str], ...] = ()


PLAYWRIGHT_SEARCH_ENGINES: dict[str, PlaywrightSearchEngineConfig] = {
    "bing": PlaywrightSearchEngineConfig(
        key="bing",
        display_name="必应",
        endpoint="https://cn.bing.com/search",
        query_param="q",
        result_selector="li.b_algo",
        link_selector="h2 a",
        title_selectors=("h2", "h2 a"),
        snippet_selectors=("p", ".b_caption p"),
        wait_selector="li.b_algo",
        static_params=(("setlang", "zh-Hans"),),
    ),
    "google": PlaywrightSearchEngineConfig(
        key="google",
        display_name="Google",
        endpoint="https://www.google.com/search",
        query_param="q",
        result_selector="div.g",
        link_selector="a",
        title_selectors=("h3",),
        snippet_selectors=("div[data-sncf]", ".VwiC3b", ".IsZvec"),
        wait_selector="div.g",
        static_params=(("hl", "zh-CN"),),
    ),
    "baidu": PlaywrightSearchEngineConfig(
        key="baidu",
        display_name="百度",
        endpoint="https://www.baidu.com/s",
        query_param="wd",
        result_selector="div.result, div.c-container",
        link_selector="h3 a, a",
        title_selectors=("h3", "h3 a"),
        snippet_selectors=(".c-abstract", ".content-right_8Zs40", ".c-span-last"),
        wait_selector="div.result, div.c-container",
    ),
    "duckduckgo": PlaywrightSearchEngineConfig(
        key="duckduckgo",
        display_name="DuckDuckGo",
        endpoint="https://duckduckgo.com/html/",
        query_param="q",
        result_selector=".result",
        link_selector=".result__a",
        title_selectors=(".result__a",),
        snippet_selectors=(".result__snippet",),
        wait_selector=".result",
    ),
}

PLAYWRIGHT_SEARCH_ENGINE_ALIASES = {
    "bing": "bing",
    "必应": "bing",
    "cn-bing": "bing",
    "google": "google",
    "谷歌": "google",
    "baidu": "baidu",
    "百度": "baidu",
    "duckduckgo": "duckduckgo",
    "ddg": "duckduckgo",
}


def resolve_playwright_search_engine(value: str | None) -> PlaywrightSearchEngineConfig:
    """解析配置中的搜索引擎名称，未知值回退为 Bing。"""

    key = PLAYWRIGHT_SEARCH_ENGINE_ALIASES.get((value or "").strip().lower(), "bing")
    return PLAYWRIGHT_SEARCH_ENGINES[key]


def normalize_web_search_configs(configs: object) -> tuple[str, ...]:
    """从前端配置列表中提取启用的联网搜索提供商标识。"""

    if not isinstance(configs, list):
        return ()
    normalized: list[str] = []
    for item in configs:
        if not isinstance(item, dict):
            continue
        key = str(item.get("provider") or item.get("key") or "").strip().lower()
        if not key:
            continue
        normalized.append(key)
    return tuple(normalized)
