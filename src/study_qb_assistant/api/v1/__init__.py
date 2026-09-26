"""API v1 规范路由入口。"""

from __future__ import annotations

from .router import build_api_v1_router

API_V1_PREFIX = "/api/v1"

__all__ = ["API_V1_PREFIX", "build_api_v1_router"]
