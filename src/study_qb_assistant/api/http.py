"""请求地址与模型可见服务地址推导。"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import Request

from ..config import get_global_config
from ..platform.settings import SettingsService


def base_url_from_request(request: Request, settings: SettingsService | None = None) -> str:
    """根据请求头与平台协议配置推导当前服务的基础 URL。"""
    config = settings.get_system_config() if settings is not None else {}
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("Host")
        or "127.0.0.1:8765"
    )
    if str(config.get("smart_proto_enabled", "true")).lower() in {"0", "false", "no", "off"}:
        proto = str(config.get("custom_proto_header") or "http").lower()
    else:
        proto = (
            request.headers.get("X-Forwarded-Proto")
            or request.url.scheme
            or str(config.get("custom_proto_header") or "http")
        ).lower()
    if proto not in {"http", "https"}:
        proto = "http"
    return f"{proto}://{host}"

def extract_client_ip(request: Request) -> str:
    """返回可审计的客户端 IP，仅信任本地反向代理提供的转发头。"""

    peer_ip = normalize_ip_address(request.client.host if request.client else "")
    if peer_ip and is_local_proxy_address(peer_ip):
        forwarded = request.headers.get("x-forwarded-for", "")
        forwarded_ip = normalize_ip_address(forwarded.split(",", maxsplit=1)[0])
        if forwarded_ip:
            return forwarded_ip
        real_ip = normalize_ip_address(request.headers.get("x-real-ip", ""))
        if real_ip:
            return real_ip
    return peer_ip


def normalize_ip_address(value: str) -> str:
    """验证并规范化单个 IPv4 或 IPv6 地址，拒绝非地址转发头内容。"""

    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return ""


def is_local_proxy_address(value: str) -> bool:
    """判断连接对端是否可能是本机或 Docker 内网中的反向代理。"""

    address = ipaddress.ip_address(value)
    return address.is_private or address.is_loopback or address.is_link_local

def model_visible_base_url(request: Request, settings: SettingsService | None = None) -> str:
    """返回模型大概率可访问的服务基础 URL；本地地址返回空串触发 data URL 兜底。"""

    configured = get_global_config().public_base_url
    if configured:
        return configured
    inferred = base_url_from_request(request, settings)
    host = urlparse(inferred).hostname or ""
    if host.lower() in {"localhost", "testserver"}:
        return ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return inferred
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
        return ""
    return inferred
