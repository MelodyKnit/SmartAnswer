"""平台用户中心相关路由。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ..context import current_user, get_platform_service, unauthorized_response
from ..route_support import build_daily_trend, count_by_key
from ..schemas import FeedbackPayload


def build_platform_user_router() -> APIRouter:
    """构建用户中心、使用日志、看板和反馈路由。"""
    router = APIRouter()

    @router.get("/users/me")
    def users_me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        return JSONResponse(
            {
                "ok": True,
                "user": user,
                "billing": platform.get_billing(),
                "wallet": platform.wallet_summary(
                    user_id=str(user["user_id"]),
                    username=str(user["username"]),
                    points=int(user["points"]),
                ),
            }
        )

    @router.get("/usage-logs")
    def usage_logs(request: Request, username: str | None = None, keyword: str = "", limit: int = 100) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        logs = platform.list_usage_logs(username=username, keyword=keyword, limit=limit)
        return JSONResponse({"ok": True, "logs": logs})

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

    @router.post("/feedback")
    def feedback_create(request: Request, payload: FeedbackPayload) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        feedback = platform.create_feedback(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            usage_log_id=payload.usage_log_id,
            title=payload.title,
            content=payload.content,
            image_urls=tuple(str(item) for item in payload.image_urls),
        )
        return JSONResponse({"ok": True, "feedback": feedback})

    @router.get("/feedback")
    def feedback_list(request: Request, username: str | None = None, limit: int = 100) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        platform = get_platform_service(request)
        if user["role"] not in {"admin", "superadmin"}:
            username = str(user["username"])
        feedbacks = platform.list_feedbacks(username=username, limit=limit)
        return JSONResponse({"ok": True, "feedbacks": feedbacks})

    return router
