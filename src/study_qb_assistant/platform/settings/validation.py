"""系统配置值校验。"""

from __future__ import annotations

from urllib.parse import urlparse

from ...auth import AuthError
from ..config import SYSTEM_CONFIG_DEFAULTS


def normalize_site_logo_url(value: str) -> str:
    """校验站点 Logo 地址，只允许站内路径或 HTTP(S) URL。"""

    text = (value or "").strip()
    if not text:
        return ""
    if len(text) > 2048:
        raise AuthError("INVALID_INPUT", "Logo 地址不能超过 2048 个字符", http_status=400)
    if text.startswith("/"):
        if text.startswith("/media/brand/"):
            return text
        if text.startswith("//") or any(ch.isspace() for ch in text):
            raise AuthError("INVALID_INPUT", "Logo 地址格式不正确", http_status=400)
        return text
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not any(
        ch.isspace() for ch in text
    ):
        return text
    raise AuthError("INVALID_INPUT", "Logo 地址仅支持站内路径或 http/https URL", http_status=400)


def normalize_email_code_policy_value(key: str, value: str) -> str:
    """校验邮箱验证码策略数值。"""

    bounds = {
        "email_code_ttl_minutes": (1, 60),
        "email_code_cooldown_seconds": (0, 3600),
        "email_code_daily_limit": (1, 100),
        "email_code_ip_hourly_limit": (1, 500),
        "email_code_max_attempts": (1, 20),
    }
    minimum, maximum = bounds[key]
    try:
        parsed = int(value or SYSTEM_CONFIG_DEFAULTS[key])
    except ValueError as exc:
        raise AuthError("INVALID_INPUT", f"{key} 必须为整数", http_status=400) from exc
    if parsed < minimum or parsed > maximum:
        raise AuthError(
            "INVALID_INPUT",
            f"{key} 必须在 {minimum} 到 {maximum} 之间",
            http_status=400,
        )
    return str(parsed)
