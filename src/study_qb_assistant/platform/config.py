"""平台领域的配置常量。"""

from __future__ import annotations

SYSTEM_CONFIG_KEYS = {
    "site_title",
    "site_logo_url",
    "smart_proto_enabled",
    "custom_proto_header",
    "default_user_points",
    "invite_bonus_points",
    "manual_grant_default_points",
    "redeem_code_default_points",
    "answer_retry_times",
    "registration_enabled",
    "email_verification_enabled",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_username",
    "smtp_password",
    "smtp_from_email",
    "smtp_from_name",
    "email_code_ttl_minutes",
    "email_code_cooldown_seconds",
    "email_code_daily_limit",
    "email_code_ip_hourly_limit",
    "email_code_max_attempts",
}

SYSTEM_CONFIG_BOOLEAN_KEYS = {
    "smart_proto_enabled",
    "registration_enabled",
    "email_verification_enabled",
}

LLM_RUNTIME_CONFIG_KEYS = {
    "llm_fallback",
    "llm_explain",
    "allow_known_rules",
    "no_local_bank_mode",
    "search_first",
    "self_consistency_repeats",
    "web_search_provider",
    "web_search_configs",
    "search_proxy",
    "llm_proxy",
    "google_search_api_key",
    "google_search_cx",
    "baidu_search_api_key",
    "llm_cache_enabled",
    "llm_cache_min_confidence",
    "llm_cache_min_confirmations",
}

SYSTEM_CONFIG_SECRET_KEYS = {"smtp_password"}

LLM_RUNTIME_SECRET_KEYS = {
    "google_search_api_key",
    "google_search_cx",
    "baidu_search_api_key",
}

SYSTEM_CONFIG_DEFAULTS = {
    "site_title": "AI题库",
    "site_logo_url": "",
    "smart_proto_enabled": "true",
    "custom_proto_header": "http",
    "default_user_points": "100",
    "invite_bonus_points": "0",
    "manual_grant_default_points": "100",
    "redeem_code_default_points": "50",
    "answer_retry_times": "3",
    "registration_enabled": "true",
    "email_verification_enabled": "false",
    "smtp_host": "",
    "smtp_port": "465",
    "smtp_security": "ssl",
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from_email": "",
    "smtp_from_name": "AI题库",
    "email_code_ttl_minutes": "10",
    "email_code_cooldown_seconds": "60",
    "email_code_daily_limit": "5",
    "email_code_ip_hourly_limit": "20",
    "email_code_max_attempts": "5",
}

LLM_RUNTIME_DEFAULTS = {
    "llm_fallback": "true",
    "llm_explain": "false",
    "allow_known_rules": "true",
    "no_local_bank_mode": "false",
    "search_first": "false",
    "self_consistency_repeats": "1",
    "web_search_provider": "duckduckgo",
    "web_search_configs": "[]",
    "search_proxy": "",
    "llm_proxy": "",
    "google_search_api_key": "",
    "google_search_cx": "",
    "baidu_search_api_key": "",
    "llm_cache_enabled": "true",
    "llm_cache_min_confidence": "0.95",
    "llm_cache_min_confirmations": "2",
}

SYSTEM_CONFIG_ENV_MAP = {
    "smart_proto_enabled": "STQB_SMART_PROTO_ENABLED",
    "custom_proto_header": "STQB_CUSTOM_PROTO_HEADER",
    "answer_retry_times": "STQB_ANSWER_RETRY_TIMES",
    "registration_enabled": "STQB_REGISTRATION_ENABLED",
}

LLM_RUNTIME_ENV_MAP = {
    "llm_fallback": "STQB_LLM_FALLBACK",
    "llm_explain": "STQB_LLM_EXPLAIN",
    "allow_known_rules": "STQB_ALLOW_KNOWN_RULES",
    "no_local_bank_mode": "STQB_NO_LOCAL_BANK_MODE",
    "search_first": "STQB_SEARCH_FIRST",
    "self_consistency_repeats": "STQB_SELF_CONSISTENCY_REPEATS",
    "web_search_provider": "STQB_WEB_SEARCH_PROVIDER",
    "search_proxy": "STQB_SEARCH_PROXY",
    "llm_proxy": "STQB_LLM_PROXY",
    "google_search_api_key": "STQB_GOOGLE_SEARCH_API_KEY",
    "google_search_cx": "STQB_GOOGLE_SEARCH_CX",
    "baidu_search_api_key": "STQB_BAIDU_SEARCH_API_KEY",
    "llm_cache_enabled": "STQB_LLM_CACHE_ENABLED",
    "llm_cache_min_confidence": "STQB_LLM_CACHE_MIN_CONFIDENCE",
    "llm_cache_min_confirmations": "STQB_LLM_CACHE_MIN_CONFIRMATIONS",
}
