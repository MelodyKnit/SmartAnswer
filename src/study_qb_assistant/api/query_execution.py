"""查题请求执行、计费审计与响应适配。"""

from __future__ import annotations

import json
import secrets
import time

from fastapi import Request
from starlette.responses import JSONResponse

from ..adapters.ocs import OcsIntegrationPort
from ..answering import AnswerService
from ..auth import AuthError, AuthService
from ..llm.tracing import reset_request_id, set_request_id
from ..logger import log_event
from ..media.inputs import legacy_image_url_only
from ..platform.settings import SettingsService
from ..platform.tokens import TokenService
from ..platform.usage import UsageService
from ..questions.models import QuestionQuery
from ..search import LocalQuestionIndex
from .dependencies import get_ocs_integration
from .http import model_visible_base_url, extract_client_ip
from .security import auth_error_response, authorization_bearer, current_user


def run_lookup(
    lookup: LocalQuestionIndex | AnswerService,
    usage: UsageService,
    tokens: TokenService,
    settings: SettingsService,
    auth: AuthService,
    request: Request,
    path: str,
    method: str,
    query: QuestionQuery,
) -> JSONResponse:
    """执行查题主流程，并完成计费、日志与响应转换。"""
    if not query.request_id:
        query.request_id = secrets.token_hex(12)
    if not query.service_base_url:
        query.service_base_url = model_visible_base_url(request, settings)
    client_ip = extract_client_ip(request)
    started = time.time()
    try:
        set_request_id(str(query.request_id or ""))
        result = lookup.query(query)
        # 将 client_ip 以 debug 的方式载入 result中
        result.debug.setdefault("client_ip", client_ip)
        if legacy_image_url_only(query):
            result.debug.setdefault("legacy_url_only", "true")
        if query.image_capture_status:
            result.debug.setdefault("image_capture_status", str(query.image_capture_status))
        if query.image_capture_failures:
            result.debug.setdefault("image_capture_failures", str(query.image_capture_failures))
        elapsed_seconds = time.time() - started
        try:
            token = record_usage(
                usage,
                tokens,
                settings,
                auth,
                request,
                query,
                result,
                elapsed_seconds,
                client_ip=client_ip,
            )
        except AuthError as exc:
            return auth_error_response(exc)
        log_query(path, method, query, result, elapsed_seconds)
        return JSONResponse(
            response_for_path(
                path,
                result,
                settings=settings,
                token=token,
                ocs_integration=get_ocs_integration(request),
            )
        )
    finally:
        reset_request_id()

def response_for_path(
    path: str,
    result,
    *,
    settings: SettingsService | None = None,
    token: dict | None = None,
    ocs_integration: OcsIntegrationPort | None = None,
) -> dict:
    """按接口类型返回标准响应结构。"""
    if path == "/ocs/query":
        if ocs_integration is None:
            from ..adapters.ocs import DefaultOcsIntegration

            ocs_integration = DefaultOcsIntegration()
        threshold = low_confidence_threshold(settings, token)
        if result.ok and threshold > 0 and float(result.confidence) < threshold:
            return ocs_integration.format_low_confidence_response(result, threshold=threshold)
        return ocs_integration.format_response(result)
    return result.to_api_dict()

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

def record_usage(
    usage: UsageService,
    tokens: TokenService,
    settings: SettingsService,
    auth: AuthService,
    request: Request,
    query: QuestionQuery,
    result,
    elapsed_seconds: float,
    client_ip: str = "",
) -> dict | None:
    """记录本次调用的积分消耗与审计日志。"""
    user = current_user(request)
    token = tokens.resolve_token(authorization_bearer(request))
    if user is None and token is None:
        return None
    if user is None and token is not None:
        user = auth.resolve_user_by_id(token["user_id"])
    if user is None:
        return token
    points_cost = settings.calculate_points_cost(str(result.resolution_mode))
    primary_source = result.sources[0] if getattr(result, "sources", ()) else {}
    source_id = str(primary_source.get("source_id") or "")
    source_type = str(primary_source.get("source_type") or "")
    question_id = (
        source_id if source_type in {"qa_record", "ai_generated_question_bank"} and source_id else None
    )
    usage.record_usage(
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
        client_ip=client_ip,
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
        "page_url": str(query.page_url or ""),
        "image_capture_status": str(query.image_capture_status or ""),
        "image_capture_failures": int(query.image_capture_failures or 0),
        "image_urls": list(query.image_urls),
        "image_data_url_count": len(query.image_data_urls),
        "legacy_url_only": legacy_image_url_only(query),
        "option_image_urls": dict(query.option_image_urls),
        "option_image_data_url_count": len(query.option_image_data_urls),
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
    settings: SettingsService | None, token: dict | None
) -> float:
    """读取当前 API Key 是否要求拒绝低置信度答案。"""

    if not token or not bool(token.get("reject_low_confidence")):
        return 0.0
    threshold = float_value(token.get("min_answer_confidence"), default=0.0)
    if threshold > 0:
        return min(max(threshold, 0.0), 1.0)
    if settings is None:
        return 0.95
    runtime_config = settings.get_llm_runtime_config()
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
