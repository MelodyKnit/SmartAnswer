"""使用记录接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....platform.usage.time_ranges import local_day_window_from_dates
from ...dependencies import get_usage_service
from ...security import current_user, unauthorized_response


def build_usage_router() -> APIRouter:
    """构建当前业务域路由。"""

    router = APIRouter()

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
        usage = get_usage_service(request)
        can_view_all = str(user["role"]) == "superadmin" or "dashboard:all" in set(
            user.get("permissions") or ()
        )
        if not can_view_all:
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
        logs = usage.list_usage_logs(
            username=username,
            token_id=selected_token_id,
            keyword=keyword,
            limit=limit,
            offset=offset,
            start_time=start_time,
            end_time=end_time,
        )
        total = usage.count_usage_logs(
            username=username,
            token_id=selected_token_id,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
        )
        return JSONResponse(
            {"ok": True, "logs": logs, "total": total, "page": page, "limit": limit}
        )

    return router
