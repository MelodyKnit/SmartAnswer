"""系统公告相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_announcement_service, get_permission_service
from ...security import (
    auth_error_response,
    current_user,
    require_permissions,
    unauthorized_response,
)
from .schemas import AnnouncementCreatePayload, AnnouncementUpdatePayload


def build_announcement_router() -> APIRouter:
    """构建公告管理与用户侧公告读取路由。"""

    router = APIRouter()

    @router.get("/announcements")
    def announcements_list(
        request: Request,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> JSONResponse:
        denied = require_permissions(request, {"announcements:read"})
        if denied:
            return denied
        platform = get_announcement_service(request)
        permission_service = get_permission_service(request)
        payload = platform.list_announcements(
            keyword=keyword,
            status=status,
            level=level,
            audience=audience,
            page=page,
            limit=limit,
        )
        payload["audience_options"] = [
            {"value": "all", "label": "全部用户"},
            *[
                {"value": role["role_id"], "label": role["name"]}
                for role in permission_service.list_roles()
            ],
        ]
        return JSONResponse({"ok": True, **payload})

    @router.get("/announcements/active")
    def announcements_active(request: Request, limit: int = 10) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_announcement_service(request)
        return JSONResponse(
            {
                "ok": True,
                "announcements": platform.list_active_announcements(
                    role=str(user["role"]),
                    limit=limit,
                ),
            }
        )

    @router.post("/announcements")
    def announcements_create(
        request: Request, payload: AnnouncementCreatePayload
    ) -> JSONResponse:
        denied = require_permissions(request, {"announcements:write"})
        if denied:
            return denied
        platform = get_announcement_service(request)
        permission_service = get_permission_service(request)
        actor = current_user(request)
        try:
            announcement = platform.create_announcement(
                title=payload.title,
                content=payload.content,
                level=payload.level,
                audience=payload.audience,
                status=payload.status,
                pinned=payload.pinned,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                created_by=str(actor["username"]) if actor else "",
                valid_role_ids={role["role_id"] for role in permission_service.list_roles()},
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "announcement": announcement})

    @router.patch("/announcements/{announcement_id}")
    def announcements_update(
        request: Request,
        announcement_id: str,
        payload: AnnouncementUpdatePayload,
    ) -> JSONResponse:
        denied = require_permissions(request, {"announcements:write"})
        if denied:
            return denied
        platform = get_announcement_service(request)
        permission_service = get_permission_service(request)
        try:
            announcement = platform.update_announcement(
                announcement_id,
                **payload.model_dump(exclude_unset=True),
                valid_role_ids={role["role_id"] for role in permission_service.list_roles()},
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "announcement": announcement})

    @router.delete("/announcements/{announcement_id}")
    def announcements_archive(request: Request, announcement_id: str) -> JSONResponse:
        denied = require_permissions(request, {"announcements:write"})
        if denied:
            return denied
        platform = get_announcement_service(request)
        permission_service = get_permission_service(request)
        try:
            announcement = platform.archive_announcement(
                announcement_id,
                valid_role_ids={role["role_id"] for role in permission_service.list_roles()},
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse(
            {
                "ok": True,
                "announcement_id": announcement["announcement_id"],
                "status": announcement["status"],
            }
        )

    return router
