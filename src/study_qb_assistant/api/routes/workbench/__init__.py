"""平台工作台与消息中心相关路由。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...context import (
    auth_error_response,
    current_user,
    get_platform_service,
    unauthorized_response,
)
from ...route_support import (
    build_daily_trend,
    count_by_key,
)


def build_workbench_router() -> APIRouter:
    """构建工作台与消息中心路由。"""
    router = APIRouter()

    @router.get("/dashboard/workbench")
    def dashboard_workbench(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        payload = platform.dashboard_workbench(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(user["points"]),
            role=str(user["role"]),
        )
        return JSONResponse({"ok": True, "workbench": payload})

    @router.get("/dashboard/rankings")
    def dashboard_rankings(
        request: Request,
        days: int = 1,
        limit: int = 10,
        dimension: str = "integration",
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        username = None
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        rankings = platform.dashboard_rankings(
            days=days, limit=limit, dimension=dimension, username=username
        )
        return JSONResponse({"ok": True, "rankings": rankings})

    @router.get("/dashboard/summary")
    def dashboard_summary(request: Request, days: int = 30) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        logs = platform.list_usage_logs(username=str(user["username"]), limit=1000)
        since = time.time() - max(1, min(days, 365)) * 86400
        scoped = [log for log in logs if float(log["created_at"]) >= since]
        trend = build_daily_trend(scoped, days)
        return JSONResponse(
            {
                "ok": True,
                "summary": {
                    "days": days,
                    "points_used": sum(int(log["points_cost"]) for log in scoped),
                    "query_count": len(scoped),
                    "resolution_modes": count_by_key(scoped, "resolution_mode"),
                    "trend": trend,
                },
            }
        )

    @router.get("/usage-logs")
    def usage_logs(
        request: Request,
        username: str | None = None,
        token_id: str = "",
        api_key_id: str = "",
        keyword: str = "",
        limit: int = 100,
        page: int = 1,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        page = max(1, int(page))
        limit = max(1, min(int(limit), 500))
        offset = (page - 1) * limit
        selected_token_id = (token_id or api_key_id).strip()
        logs = platform.list_usage_logs(
            username=username,
            token_id=selected_token_id,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        total = platform.count_usage_logs(
            username=username, token_id=selected_token_id, keyword=keyword
        )
        return JSONResponse(
            {"ok": True, "logs": logs, "total": total, "page": page, "limit": limit}
        )

    @router.get("/notifications")
    def notifications(request: Request, status: str = "", limit: int = 20) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        items = platform.list_notifications(
            user_id=str(user["user_id"]), status=status, limit=limit
        )
        return JSONResponse({"ok": True, "notifications": items})

    @router.post("/notifications/{notification_id}/read")
    def notification_read(request: Request, notification_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            item = platform.mark_notification_read(
                notification_id,
                user_id=str(user["user_id"]),
                read=True,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "notification": item})

    @router.post("/notifications/read-all")
    def notification_read_all(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        count = platform.mark_all_notifications_read(user_id=str(user["user_id"]))
        return JSONResponse({"ok": True, "count": count})

    return router
