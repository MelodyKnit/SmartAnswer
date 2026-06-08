"""API 路由共用的业务辅助逻辑。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import Request
from starlette.responses import JSONResponse

from ..adapters import to_ocs_response
from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..models import QuestionQuery
from ..platform import PlatformService
from ..runtime_log import log_event, recent_events
from ..search import LocalQuestionIndex
from .context import authorization_bearer, current_user

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_PAGES = {
    "/": "index.html",
    "/dashboard": "index.html",
    "/dashboard.html": "index.html",
    "/index.html": "index.html",
}


def run_lookup(
    lookup: LocalQuestionIndex | AnswerService,
    platform: PlatformService,
    auth: AuthService,
    request: Request,
    path: str,
    method: str,
    query: QuestionQuery,
) -> JSONResponse:
    """执行查题主流程，并完成计费、日志与响应转换。"""
    started = time.time()
    result = lookup.query(query)
    record_usage(platform, auth, request, query, result)
    log_query(path, method, query, result, time.time() - started)
    return JSONResponse(response_for_path(path, result))


def response_for_path(path: str, result) -> dict:
    """按接口类型返回标准响应结构。"""
    if path == "/ocs/query":
        return to_ocs_response(result)
    return result.to_api_dict()


def status_payload(lookup: LocalQuestionIndex | AnswerService) -> dict:
    """构造服务状态响应。"""
    status = lookup.status()
    return {
        "ok": True,
        "service": "study-question-bank-assistant",
        **status,
    }


def debug_events_payload() -> dict[str, object]:
    """返回最近一批结构化事件。"""
    return {"ok": True, "events": recent_events()}


def log_query(path: str, method: str, query: QuestionQuery, result, elapsed_seconds: float) -> None:
    """记录统一的查题行为日志。"""
    answer = result.candidate_answer or result.answer_text
    log_event(
        "query",
        {
            "method": method,
            "path": path,
            "title": query.title,
            "title_length": len(query.title),
            "options_count": len(query.options),
            "options": list(query.options)[:8],
            "question_type": query.question_type,
            "ok": result.ok,
            "answer": answer,
            "answer_raw": result.candidate_answer,
            "answer_text": result.answer_text,
            "resolution_mode": result.resolution_mode,
            "confidence": result.confidence,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "elapsed_ms": round(elapsed_seconds * 1000, 2),
        },
    )
    if path == "/ocs/query" and not result.candidate_answer and result.answer_text:
        log_event(
            "ocs_answer_fallback_used",
            {
                "title": query.title,
                "question_type": query.question_type,
                "answer_text": result.answer_text,
                "resolution_mode": result.resolution_mode,
            },
        )


def base_url_from_request(request: Request) -> str:
    """根据请求头推导当前服务的基础 URL。"""
    host = request.headers.get("Host") or "127.0.0.1:8765"
    return f"http://{host}"


def base_url_from_headers(headers) -> str:
    """兼容旧测试中 header-like 映射的基础 URL 推导。"""
    host = headers.get("Host") or "127.0.0.1:8765"
    return f"http://{host}"


def build_session_cookie(token: str, max_age: int | None) -> str:
    """构造会话 Cookie 字符串。"""
    from .context import SESSION_COOKIE

    parts = [f"{SESSION_COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict"]
    if max_age is not None:
        parts.append(f"Max-Age={int(max_age)}")
    return "; ".join(parts)


def expire_session_cookie() -> str:
    """构造删除会话 Cookie 的响应头值。"""
    from .context import SESSION_COOKIE

    return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"


def record_usage(
    platform: PlatformService,
    auth: AuthService,
    request: Request,
    query: QuestionQuery,
    result,
) -> None:
    """记录本次调用的积分消耗与审计日志。"""
    user = current_user(request)
    token = platform.resolve_token(authorization_bearer(request))
    if user is None and token is None:
        return
    if user is None and token is not None:
        user = auth.resolve_user_by_id(token["user_id"])
    if user is None:
        return
    if platform.has_active_subscription(str(user["user_id"])):
        points_cost = 0
    else:
        points_cost = platform.calculate_points_cost(str(result.resolution_mode))
        try:
            auth.consume_points(str(user["username"]), points_cost)
        except AuthError:
            points_cost = 0
    platform.record_usage(
        user_id=str(user["user_id"]),
        username=str(user["username"]),
        token_id=(str(token["token_id"]) if token else None),
        title=query.title,
        question_type=query.question_type,
        resolution_mode=str(result.resolution_mode),
        answer=result.candidate_answer or result.answer_text,
        confidence=float(result.confidence),
        provider=str(result.debug.get("provider") or ""),
        points_cost=points_cost,
    )


def count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """统计字典列表中某个字段的频次。"""
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_daily_trend(logs: list[dict], days: int) -> list[dict]:
    """按天聚合查询次数与积分消耗。"""
    buckets: dict[str, dict[str, int]] = {}
    now = time.time()
    for offset in range(days):
        day_ts = now - ((days - offset - 1) * 86400)
        day = time.strftime("%Y-%m-%d", time.localtime(day_ts))
        buckets[day] = {"date": day, "query_count": 0, "points_used": 0}
    for log in logs:
        day = time.strftime("%Y-%m-%d", time.localtime(float(log["created_at"])))
        if day not in buckets:
            continue
        buckets[day]["query_count"] += 1
        buckets[day]["points_used"] += int(log["points_cost"])
    return list(buckets.values())


def apply_system_config_to_process(platform: PlatformService) -> None:
    """把系统配置写回当前进程环境变量。"""
    for env_key, value in platform.runtime_env().items():
        os.environ[env_key] = value
