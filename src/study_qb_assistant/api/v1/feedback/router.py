"""平台反馈相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ...dependencies import get_feedback_service
from ...security import (
    auth_error_response,
    current_user,
    require_permissions,
    unauthorized_response,
)
from .schemas import FeedbackPayload, FeedbackResolvePayload


def build_feedback_router() -> APIRouter:
    """构建反馈域路由。"""
    router = APIRouter()

    @router.post("/feedback")
    def feedback_create(request: Request, payload: FeedbackPayload) -> JSONResponse:
        denied = require_permissions(request, {"feedback:self"})
        if denied:
            return denied
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        feedback_service = get_feedback_service(request)
        feedback = feedback_service.create_feedback(
            user_id=str(user["user_id"]),
            username=str(user["username"]),
            usage_log_id=payload.usage_log_id,
            title=payload.title,
            content=payload.content,
            image_urls=tuple(str(item) for item in payload.image_urls),
            category=payload.category,
        )
        return JSONResponse({"ok": True, "feedback": feedback})

    @router.get("/feedback")
    def feedback_list(
        request: Request,
        username: str | None = None,
        status: str = "",
        category: str = "",
        limit: int = 100,
        page: int = 1,
    ) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        feedback_service = get_feedback_service(request)
        can_manage = require_permissions(request, {"feedback:manage"}) is None
        if not can_manage:
            username = str(user["username"])
        page = max(1, int(page))
        limit = max(1, min(int(limit), 500))
        offset = (page - 1) * limit
        feedbacks = feedback_service.list_feedbacks(
            username=username, status=status, category=category, limit=limit, offset=offset
        )
        total = feedback_service.count_feedbacks(
            username=username, status=status, category=category
        )
        return JSONResponse(
            {"ok": True, "feedbacks": feedbacks, "total": total, "page": page, "limit": limit}
        )

    @router.patch("/feedback/{feedback_id}")
    def feedback_resolve(
        request: Request, feedback_id: str, payload: FeedbackResolvePayload
    ) -> JSONResponse:
        denied = require_permissions(request, {"feedback:manage"})
        if denied:
            return denied
        actor = current_user(request)
        if actor is None:
            return unauthorized_response("请先登录")
        feedback_service = get_feedback_service(request)
        try:
            feedback, granted = feedback_service.resolve_feedback(
                feedback_id,
                handled_by=str(actor["username"]),
                status=payload.status,
                admin_note=payload.admin_note,
                corrected_answer=payload.corrected_answer,
                reward_points=payload.reward_points,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "feedback": feedback, "granted_points": granted})

    return router
