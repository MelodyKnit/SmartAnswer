"""工作台聚合接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ...dependencies import get_dashboard_service
from ...security import current_user, unauthorized_response


def build_dashboard_router() -> APIRouter:
    """构建当前业务域路由。"""

    router = APIRouter()

    @router.get("/dashboard/workbench")
    def dashboard_workbench(request: Request, scope: str = "") -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        dashboard = get_dashboard_service(request)
        payload = dashboard.dashboard_workbench(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            points=int(user["points"]),
            role=str(user["role"]),
            scope=scope,
            permissions=set(user.get("permissions") or ()),
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
        dashboard = get_dashboard_service(request)
        rankings = dashboard.dashboard_rankings(
            days=days,
            limit=limit,
            dimension=dimension,
            username=str(user["username"]),
            role=str(user["role"]),
            scope=scope,
            permissions=set(user.get("permissions") or ()),
        )
        return JSONResponse({"ok": True, "rankings": rankings})

    @router.get("/dashboard/summary")
    def dashboard_summary(request: Request, days: int = 30, scope: str = "") -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        dashboard = get_dashboard_service(request)
        return JSONResponse(
            {
                "ok": True,
                "summary": dashboard.dashboard_summary(
                    username=str(user["username"]),
                    role=str(user["role"]),
                    scope=scope,
                    days=days,
                    permissions=set(user.get("permissions") or ()),
                ),
            }
        )

    return router
