"""认证与会话相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ....auth.email_verification import EmailVerificationService, normalize_email
from ...dependencies import get_auth_service, get_settings_service
from ...security import (
    SESSION_COOKIE,
    auth_error_response,
    current_user,
    session_token_from_request,
    unauthorized_response,
)
from ....logger import console_log
from .schemas import (
    EmailVerificationCodePayload,
    LoginPayload,
    RegisterPayload,
    ResetConfirmPayload,
    ResetRequestPayload,
)


def build_auth_router() -> APIRouter:
    """构建认证域路由。"""
    router = APIRouter()

    @router.get("/auth/session")
    def session(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        return JSONResponse({"ok": True, "user": user})

    @router.post("/auth/register")
    def register(request: Request, payload: RegisterPayload) -> JSONResponse:
        auth = get_auth_service(request)
        platform = get_settings_service(request)
        if auth.has_users() and not platform.is_registration_enabled():
            return auth_error_response(
                AuthError(
                    "REGISTRATION_DISABLED", "系统已关闭用户注册", http_status=403
                )
            )
        try:
            email_code_record = None
            verification = None
            email = normalize_email(payload.email) if str(payload.email or "").strip() else None
            auth.assert_invite_code_valid(payload.invite_code)
            if platform.is_registration_email_required() and not email:
                raise AuthError("EMAIL_REQUIRED", "请填写邮箱", http_status=400)
            if platform.is_email_verification_enabled():
                if not email or not payload.email_code:
                    raise AuthError(
                        "EMAIL_VERIFICATION_REQUIRED",
                        "请先完成邮箱验证码校验",
                        http_status=400,
                    )
                verification = email_verification_service(request)
                email_code_record = verification.verify(
                    email=email,
                    purpose="register",
                    code=payload.email_code,
                )
            user = auth.register(
                payload.username,
                payload.password,
                email,
                invite_code=payload.invite_code,
                invite_bonus=platform.get_invite_bonus()
                if payload.invite_code.strip()
                else 0,
                initial_points=platform.get_default_user_points(),
            )
            if verification is not None and email_code_record is not None:
                verification.consume_code(email_code_record.code_id)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "user": user})

    @router.post("/auth/email-verification-codes")
    def send_email_verification_code(
        request: Request, payload: EmailVerificationCodePayload
    ) -> JSONResponse:
        auth = get_auth_service(request)
        platform = get_settings_service(request)
        if auth.has_users() and not platform.is_registration_enabled():
            return auth_error_response(
                AuthError(
                    "REGISTRATION_DISABLED", "系统已关闭用户注册", http_status=403
                )
            )
        if not platform.is_email_verification_enabled():
            return auth_error_response(
                AuthError(
                    "EMAIL_VERIFICATION_DISABLED",
                    "当前未启用邮箱验证码注册",
                    http_status=400,
                )
            )
        try:
            cooldown_seconds = email_verification_service(request).send_code(
                email=payload.email,
                purpose=payload.purpose,
                client_ip=request.client.host if request.client else "",
            )
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse(
            {
                "ok": True,
                "message": "验证码已发送，请查看邮箱",
                "cooldown_seconds": cooldown_seconds,
            }
        )

    @router.get("/auth/register-status")
    def register_status(request: Request) -> JSONResponse:
        auth = get_auth_service(request)
        platform = get_settings_service(request)
        config_enabled = platform.is_registration_enabled()
        first_user_allowed = not auth.has_users()
        return JSONResponse(
            {
                "ok": True,
                "registration_enabled": config_enabled or first_user_allowed,
                "config_enabled": config_enabled,
                "first_user_allowed": first_user_allowed,
                "email_registration_mode": platform.get_registration_email_mode(),
                "email_verification_enabled": platform.is_email_verification_enabled(),
                "email_required": platform.is_registration_email_required(),
            }
        )

    @router.post("/auth/login")
    def login(request: Request, payload: LoginPayload) -> JSONResponse:
        auth = get_auth_service(request)
        try:
            token, user, ttl = auth.login(
                payload.username,
                payload.password,
                remember=payload.remember,
                client_ip=request.client.host if request.client else "",
            )
        except AuthError as exc:
            return auth_error_response(exc)
        response = JSONResponse(
            {"ok": True, "user": user, "token": token, "expires_in": ttl}
        )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            path="/",
            httponly=True,
            samesite="strict",
            max_age=ttl if payload.remember else None,
        )
        return response

    @router.post("/auth/logout")
    def logout(request: Request) -> JSONResponse:
        auth = get_auth_service(request)
        auth.logout(session_token_from_request(request))
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @router.post("/auth/reset-request")
    def reset_request(
        request: Request, payload: ResetRequestPayload
    ) -> dict[str, str | bool]:
        auth = get_auth_service(request)
        token = auth.create_reset_token(payload.username)
        if token is not None:
            console_log(
                "WARNING",
                f"[密码重置] 用户 {payload.username} 的一次性重置令牌（30 分钟内有效）：{token}",
                logger_name="study_qb_assistant.auth",
            )
        return {
            "ok": True,
            "message": "若该账号存在，重置令牌已打印到服务器控制台，请联系本机管理员获取",
        }

    @router.post("/auth/reset-confirm")
    def reset_confirm(request: Request, payload: ResetConfirmPayload) -> JSONResponse:
        auth = get_auth_service(request)
        try:
            auth.confirm_reset(payload.username, payload.token, payload.new_password)
        except AuthError as exc:
            return auth_error_response(exc)
        return JSONResponse({"ok": True, "message": "密码已重置，请使用新密码登录"})

    return router


def email_verification_service(request: Request) -> EmailVerificationService:
    """构建邮箱验证码服务，测试环境可通过 app.state.email_sender 注入发送器。"""

    platform = get_settings_service(request)
    auth = get_auth_service(request)
    return EmailVerificationService(
        auth.repository,
        config=platform.get_system_config(reveal_secret=True),
        sender=getattr(request.app.state, "email_sender", None),
    )
