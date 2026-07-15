"""API 版本前缀与旧路径兼容标记。"""

from __future__ import annotations

from fastapi import Request

API_V1_PREFIX = "/api/v1"


def unversioned_api_path(path: str) -> str:
    """移除规范 API 前缀，供兼容鉴权规则复用。"""

    if path == API_V1_PREFIX:
        return "/"
    if path.startswith(f"{API_V1_PREFIX}/"):
        return path[len(API_V1_PREFIX) :]
    return path


def mark_legacy_api_request(request: Request) -> None:
    """标记当前请求使用了临时保留的无版本旧路径。"""

    request.state.legacy_api = True


def successor_path(path: str) -> str:
    """生成旧业务路径对应的 v1 规范路径。"""

    normalized = path if path.startswith("/") else f"/{path}"
    return f"{API_V1_PREFIX}{normalized}"
