"""API 路由共用的业务辅助逻辑。"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Request
from starlette.responses import JSONResponse

from ..adapters import to_ocs_low_confidence_response, to_ocs_response
from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..models import QuestionQuery
from ..platform import PlatformService
from ..platform.service import local_day_range_from_text
from ..logger import log_event, log_path, recent_events
from ..search import LocalQuestionIndex
from ..llm.tracing import reset_request_id, set_request_id
from .context import auth_error_response, authorization_bearer, current_user

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
    if not query.request_id:
        query.request_id = secrets.token_hex(12)
    started = time.time()
    try:
        set_request_id(str(query.request_id or ""))
        result = lookup.query(query)
        elapsed_seconds = time.time() - started
        try:
            token = record_usage(platform, auth, request, query, result, elapsed_seconds)
        except AuthError as exc:
            return auth_error_response(exc)
        log_query(path, method, query, result, elapsed_seconds)
        return JSONResponse(response_for_path(path, result, platform=platform, token=token))
    finally:
        reset_request_id()


def should_serve_spa_shell(request: Request, path: str) -> bool:
    """判断当前请求是否是浏览器前端导航。

    这里不维护 API 路径清单：浏览器导航由 `Accept: text/html` 表达，
    API 调用由 JSON/默认 Accept 表达，新增接口不需要同步修改该判断。
    """
    normalized = path.strip("/")
    if not normalized:
        return True
    if "." in Path(normalized).name:
        return False
    accept = request.headers.get("Accept", "").lower()
    if "text/html" in accept:
        return True

    # 某些浏览器或代理在页面刷新时不会稳定带上 text/html，
    # 但仍会通过 Fetch Metadata 标识这是一次真实文档导航。
    fetch_mode = request.headers.get("Sec-Fetch-Mode", "").lower()
    fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
    return fetch_mode == "navigate" and fetch_dest in {"document", "iframe"}


def response_for_path(
    path: str,
    result,
    *,
    platform: PlatformService | None = None,
    token: dict | None = None,
) -> dict:
    """按接口类型返回标准响应结构。"""
    if path == "/ocs/query":
        threshold = low_confidence_threshold(platform, token)
        if result.ok and threshold > 0 and float(result.confidence) < threshold:
            return to_ocs_low_confidence_response(result, threshold=threshold)
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


def debug_events_payload(start_date: str = "", end_date: str = "") -> dict[str, object]:
    """返回最近一批结构化事件，支持根据日期区间过滤本地日志文件。"""
    limit = 2000
    start_date = start_date.strip()
    end_date = end_date.strip()

    if not start_date and not end_date:
        return {"ok": True, "events": recent_events()}

    path = log_path()
    if not path.exists():
        return {"ok": True, "events": []}

    if start_date and not end_date:
        end_date = start_date
    elif end_date and not start_date:
        start_date = end_date

    start_label, _start_time, _start_end = local_day_range_from_text(start_date)
    end_label, _end_start, _end_time = local_day_range_from_text(end_date)
    if start_label > end_label:
        raise ValueError("日期范围无效")

    events = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                event_dict = json.loads(line_str)
            except json.JSONDecodeError:
                continue
            ts = event_dict.get("ts")
            if not ts or len(str(ts)) < 10:
                continue
            event_date = str(ts)[:10]
            if start_label <= event_date <= end_label:
                events.append(event_dict)

    return {"ok": True, "events": events[-limit:]}


def log_query(path: str, method: str, query: QuestionQuery, result, elapsed_seconds: float) -> None:
    """记录统一的查题行为日志。"""
    answer = result.candidate_answer or result.answer_text
    log_event(
        "query",
        {
            "request_id": query.request_id,
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


def base_url_from_request(request: Request, platform: PlatformService | None = None) -> str:
    """根据请求头与平台协议配置推导当前服务的基础 URL。"""
    config = platform.get_system_config() if platform is not None else {}
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("Host")
        or "127.0.0.1:8765"
    )
    if str(config.get("smart_proto_enabled", "true")).lower() in {"0", "false", "no", "off"}:
        proto = str(config.get("custom_proto_header") or "http").lower()
    else:
        proto = (
            request.headers.get("X-Forwarded-Proto")
            or request.url.scheme
            or str(config.get("custom_proto_header") or "http")
        ).lower()
    if proto not in {"http", "https"}:
        proto = "http"
    return f"{proto}://{host}"


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
    elapsed_seconds: float,
) -> dict | None:
    """记录本次调用的积分消耗与审计日志。"""
    user = current_user(request)
    token = platform.resolve_token(authorization_bearer(request))
    if user is None and token is None:
        return None
    if user is None and token is not None:
        user = auth.resolve_user_by_id(token["user_id"])
    if user is None:
        return token
    points_cost = platform.calculate_points_cost(str(result.resolution_mode))
    primary_source = result.sources[0] if getattr(result, "sources", ()) else {}
    source_id = str(primary_source.get("source_id") or "")
    source_type = str(primary_source.get("source_type") or "")
    question_id = (
        source_id if source_type in {"qa_record", "ai_generated_question_bank"} and source_id else None
    )
    platform.record_usage(
        user_id=str(user["user_id"]),
        username=str(user["username"]),
        token_id=(str(token["token_id"]) if token else None),
        title=query.title,
        question_type=query.question_type,
        resolution_mode=str(result.resolution_mode),
        answer=result.candidate_answer or result.answer_text,
        confidence=float(result.confidence),
        provider=usage_provider_name(result),
        points_cost=points_cost,
        elapsed_ms=round(max(0.0, elapsed_seconds) * 1000, 2),
        request_id=str(query.request_id or ""),
        question_id=question_id,
        source_name=str(primary_source.get("source_name") or ""),
        source_type=source_type,
        source_id=source_id,
        source_url=str(primary_source.get("source_url") or ""),
        context_json=usage_context_json(query, result),
    )
    return token


def usage_context_json(query: QuestionQuery, result) -> str:
    """构造 usage log 的请求上下文快照。"""

    payload = {
        "options": list(query.options),
        "image_urls": list(query.image_urls),
        "option_image_urls": dict(query.option_image_urls),
        "input_flags": [
            flag
            for flag in str(getattr(result, "debug", {}).get("input_flags", "")).split(",")
            if flag
        ],
        "error_code": getattr(result, "error_code", None),
        "error_message": getattr(result, "error_message", None),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def low_confidence_threshold(
    platform: PlatformService | None, token: dict | None
) -> float:
    """读取当前 API Key 是否要求拒绝低置信度答案。"""

    if not token or not bool(token.get("reject_low_confidence")):
        return 0.0
    threshold = float_value(token.get("min_answer_confidence"), default=0.0)
    if threshold > 0:
        return min(max(threshold, 0.0), 1.0)
    if platform is None:
        return 0.95
    runtime_config = platform.get_llm_runtime_config()
    return min(
        max(float_value(runtime_config.get("llm_cache_min_confidence"), default=0.95), 0.0),
        1.0,
    )


def float_value(value: object, *, default: float) -> float:
    """安全解析浮点数。"""

    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """统计字典列表中某个字段的频次。"""
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_daily_trend(logs: list[dict], days: int) -> list[dict]:
    """按天聚合查询次数与积分消耗。"""
    buckets: dict[str, dict[str, object]] = {}
    now = time.time()
    for offset in range(days):
        day_ts = now - ((days - offset - 1) * 86400)
        day = time.strftime("%Y-%m-%d", time.localtime(day_ts))
        buckets[day] = {"date": day, "query_count": 0, "points_used": 0}
    for log in logs:
        day = time.strftime("%Y-%m-%d", time.localtime(float(log["created_at"])))
        if day not in buckets:
            continue
        buckets[day]["query_count"] = int(str(buckets[day]["query_count"])) + 1
        buckets[day]["points_used"] = int(str(buckets[day]["points_used"])) + int(
            log["points_cost"]
        )
    return list(buckets.values())


def apply_system_config_to_process(platform: PlatformService) -> None:
    """把系统配置写回当前进程环境变量。"""
    for env_key, value in platform.runtime_env().items():
        os.environ[env_key] = value


def usage_provider_name(result) -> str:
    """为 usage log 解析稳定的 provider 名称。"""

    provider = str(result.debug.get("provider") or "").strip()
    if provider:
        return provider
    if result.sources:
        source_name = str(result.sources[0].get("source_name") or "").strip()
        if source_name:
            return source_name
    return "unknown"
