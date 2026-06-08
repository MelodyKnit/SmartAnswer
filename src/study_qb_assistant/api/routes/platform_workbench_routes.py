"""平台工作台与消息中心相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...auth import AuthError
from ..context import auth_error_response, current_user, get_platform_service, unauthorized_response


def build_platform_workbench_router() -> APIRouter:
    """构建工作台聚合、排行和消息中心路由。"""
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
        rankings = platform.dashboard_rankings(days=days, limit=limit, dimension=dimension)
        return JSONResponse({"ok": True, "rankings": rankings})

    @router.get("/notifications")
    def notifications(request: Request, status: str = "", limit: int = 20) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        items = platform.list_notifications(user_id=str(user["user_id"]), status=status, limit=limit)
        return JSONResponse({"ok": True, "notifications": items})

    @router.post("/notifications/{notification_id}/read")
    def notification_read(request: Request, notification_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            item = platform.mark_notification_read(notification_id, read=True)
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
