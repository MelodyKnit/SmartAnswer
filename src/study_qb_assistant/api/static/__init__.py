"""前端静态资源和 SPA 页面路由。"""

from .router import STATIC_DIR, build_static_router, should_serve_spa_shell

__all__ = ["STATIC_DIR", "build_static_router", "should_serve_spa_shell"]
