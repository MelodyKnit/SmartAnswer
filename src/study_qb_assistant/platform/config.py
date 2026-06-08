"""平台领域的配置常量。"""

from __future__ import annotations

SYSTEM_CONFIG_KEYS = {
    "llm_base_url",
    "llm_model",
    "llm_api_key",
    "llm_stream",
    "llm_fallback",
    "llm_explain",
    "web_search_provider",
    "search_proxy",
    "llm_proxy",
    "google_search_api_key",
    "google_search_cx",
    "baidu_search_api_key",
    "ai_cache_enabled",
    "ai_cache_min_confidence",
    "ai_cache_min_confirmations",
}

SYSTEM_CONFIG_SECRET_KEYS = {
    "llm_api_key",
    "google_search_api_key",
    "google_search_cx",
    "baidu_search_api_key",
}

SYSTEM_CONFIG_ENV_MAP = {
    "llm_base_url": "STQB_LLM_BASE_URL",
    "llm_model": "STQB_LLM_MODEL",
    "llm_api_key": "STQB_LLM_API_KEY",
    "llm_stream": "STQB_LLM_STREAM",
    "llm_fallback": "STQB_LLM_FALLBACK",
    "llm_explain": "STQB_LLM_EXPLAIN",
    "web_search_provider": "STQB_WEB_SEARCH_PROVIDER",
    "search_proxy": "STQB_SEARCH_PROXY",
    "llm_proxy": "STQB_LLM_PROXY",
    "google_search_api_key": "STQB_GOOGLE_SEARCH_API_KEY",
    "google_search_cx": "STQB_GOOGLE_SEARCH_CX",
    "baidu_search_api_key": "STQB_BAIDU_SEARCH_API_KEY",
    "ai_cache_enabled": "STQB_AI_CACHE_ENABLED",
    "ai_cache_min_confidence": "STQB_AI_CACHE_MIN_CONFIDENCE",
    "ai_cache_min_confirmations": "STQB_AI_CACHE_MIN_CONFIRMATIONS",
}
