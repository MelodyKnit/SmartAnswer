"""通知中心接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_notification_service
from ...security import auth_error_response, current_user, unauthorized_response


def build_notification_router() -> APIRouter:
    """构建当前业务域路由。"""

    router = APIRouter()

    @router.get("/notifications")
    def notifications(request: Request, status: str = "", limit: int = 20) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        notifications_service = get_notification_service(request)
        items = notifications_service.list_notifications(
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
        notifications_service = get_notification_service(request)
        try:
            payload = notifications_service.notification_center(
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
        notifications_service = get_notification_service(request)
        try:
            item = notifications_service.mark_notification_center_item_read(
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
        notifications_service = get_notification_service(request)
        count = notifications_service.mark_all_notification_center_read(
            user_id=str(user["user_id"]),
            role=str(user["role"]),
        )
        return JSONResponse({"ok": True, "count": count})

    @router.post("/notifications/{notification_id}/read")
    def notification_read(request: Request, notification_id: str) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        notifications_service = get_notification_service(request)
        try:
            item = notifications_service.mark_notification_read(
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
        notifications_service = get_notification_service(request)
        count = notifications_service.mark_all_notifications_read(
            user_id=str(user["user_id"])
        )
        return JSONResponse({"ok": True, "count": count})

    return router
