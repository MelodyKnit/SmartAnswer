"""平台工作台与消息中心相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ....platform.service import local_day_window_from_dates
from ...context import (
    auth_error_response,
    current_user,
    get_platform_service,
    unauthorized_response,
)


def build_workbench_router() -> APIRouter:
    """构建工作台与消息中心路由。"""
    router = APIRouter()

    @router.get("/dashboard/workbench")
    def dashboard_workbench(request: Request, scope: str = "") -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        payload = platform.dashboard_workbench(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(user["points"]),
            role=str(user["role"]),
            scope=scope,
        )
        return JSONResponse({"ok": True, "workbench": payload})

    @router.get("/dashboard/rankings")
    def dashboard_rankings(
        request: Request,
        days: int = 1,
        limit: int = 10,
        dimension: str = "provider",
        scope: str = "",
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        rankings = platform.dashboard_rankings(
            days=days,
            limit=limit,
            dimension=dimension,
            username=str(user["username"]),
            role=str(user["role"]),
            scope=scope,
        )
        return JSONResponse({"ok": True, "rankings": rankings})

    @router.get("/dashboard/summary")
    def dashboard_summary(request: Request, days: int = 30, scope: str = "") -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        return JSONResponse(
            {
                "ok": True,
                "summary": platform.dashboard_summary(
                    username=str(user["username"]),
                    role=str(user["role"]),
                    scope=scope,
                    days=days,
                ),
            }
        )

    @router.get("/usage-logs")
    def usage_logs(
        request: Request,
        username: str | None = None,
        token_id: str = "",
        api_key_id: str = "",
        keyword: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 100,
        page: int = 1,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        try:
            start_time, end_time = local_day_window_from_dates(start_date, end_date)
        except ValueError:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "INVALID_DATE",
                        "message": "日期格式必须为 YYYY-MM-DD，且开始日期不能晚于结束日期",
                    },
                },
                status_code=400,
            )

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
            start_time=start_time,
            end_time=end_time,
        )
        total = platform.count_usage_logs(
            username=username,
            token_id=selected_token_id,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
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

    @router.get("/notification-center")
    def notification_center(
        request: Request,
        status: str = "",
        source: str = "",
        limit: int = 20,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            payload = platform.notification_center(
                user_id=str(user["user_id"]),
                role=str(user["role"]),
                status=status,
                source=source,
                limit=limit,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, **payload})

    @router.post("/notification-center/{source}/{item_id}/read")
    def notification_center_read(
        request: Request,
        source: str,
        item_id: str,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        try:
            item = platform.mark_notification_center_item_read(
                user_id=str(user["user_id"]),
                role=str(user["role"]),
                source=source,
                item_id=item_id,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "item": item})

    @router.post("/notification-center/read-all")
    def notification_center_read_all(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        count = platform.mark_all_notification_center_read(
            user_id=str(user["user_id"]),
            role=str(user["role"]),
        )
        return JSONResponse({"ok": True, "count": count})

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
