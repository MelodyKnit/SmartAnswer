"""API v1 规范路由入口。"""

from __future__ import annotations

from ..legacy import API_V1_PREFIX
from .router import build_api_v1_router


__all__ = ["API_V1_PREFIX", "build_api_v1_router"]
