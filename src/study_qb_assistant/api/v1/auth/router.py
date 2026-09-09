"""认证与会话相关路由。"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Body, Request
from starlette.responses import JSONResponse

from ....auth import AuthError
from ....auth.email_verification import EmailVerificationService, normalize_email
from ....auth.security import THROTTLE_MAX_FAILURES
from ....platform.wallet.records import WalletOrderRecord
from ...dependencies import (
    get_auth_service,
    get_notification_service,
    get_settings_service,
    get_slider_captcha_service,
    get_wallet_service,
)
from ...security import (
    SESSION_COOKIE,
    auth_error_response,
    current_user,
    session_token_from_request,
    unauthorized_response,
)
from ....logger import console_log, log_event
from .schemas import (
    EmailVerificationCodePayload,
    LoginPayload,
    RegisterPayload,
    ResetConfirmPayload,
    ResetRequestPayload,
    SliderVerifyPayload,
)


def build_auth_router() -> APIRouter:
    """构建认证域路由。"""
    router = APIRouter()

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else ""

    def is_config_enabled(config: dict, key: str, *, default: bool) -> bool:
        value = str(config.get(key, "true" if default else "false")).strip().lower()
        return value not in {"0", "false", "no", "off", "disabled"}

    def login_failure_threshold(config: dict) -> int:
        try:
            value = int(config.get("login_failure_threshold") or 2)
        except (TypeError, ValueError):
            value = 2
        return min(max(value, 1), THROTTLE_MAX_FAILURES - 1)

    @router.get("/auth/session")
    def session(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return unauthorized_response("请先登录")
        return JSONResponse({"ok": True, "user": user})

    @router.get("/auth/captcha/slider")
    def slider_captcha_challenge(request: Request) -> JSONResponse:
        """生成一个滑块拼图挑战。"""
        slider_service = get_slider_captcha_service(request)
        challenge = slider_service.create_challenge(client_ip=client_ip(request))
        return JSONResponse({"ok": True, **challenge})

    @router.post("/auth/captcha/slider/verify")
    def slider_captcha_verify(request: Request, payload: SliderVerifyPayload) -> JSONResponse:
        """核验滑块拖拽偏移量。"""
        slider_service = get_slider_captcha_service(request)
        captcha_token = slider_service.verify_challenge(
            payload.challenge_id, payload.x, client_ip=client_ip(request)
        )
        if captcha_token is None:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": "CAPTCHA_FAILED", "message": "滑块验证未通过，请重试"},
                },
                status_code=400,
            )
        return JSONResponse({"ok": True, "captcha_token": captcha_token})

    @router.post("/auth/register")
    def register(
        request: Request,
        payload: RegisterPayload = Body(default_factory=RegisterPayload),
    ) -> JSONResponse:
        auth = get_auth_service(request)
        platform = get_settings_service(request)
        notification_service = get_notification_service(request)
        if auth.has_users() and not platform.is_registration_enabled():
            return auth_error_response(
                AuthError(
                    "REGISTRATION_DISABLED", "系统已关闭用户注册", http_status=403
                )
            )
        # 检查是否启用了注册滑块验证
        sys_config = platform.get_system_config()
        reg_captcha_enabled = is_config_enabled(
            sys_config, "registration_captcha_enabled", default=False
        )
        captcha_token_str = payload.get_clean_captcha_token()
        if reg_captcha_enabled:
            if not captcha_token_str:
                return JSONResponse(
                    {"ok": False, "error": {"code": "CAPTCHA_REQUIRED", "message": "请先完成滑块验证"}},
                    status_code=400,
                )
            slider_service = get_slider_captcha_service(request)
            if not slider_service.consume_token(
                captcha_token_str, client_ip=client_ip(request)
            ):
                return JSONResponse(
                    {"ok": False, "error": {"code": "CAPTCHA_INVALID", "message": "滑块验证凭证已失效，请重新验证"}},
                    status_code=400,
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
            invite_reward = platform.get_invite_reward_policy()
            has_invite_code = bool(payload.invite_code.strip())
            inviter_bonus = int(invite_reward["inviter_points"]) if has_invite_code else 0
            invitee_bonus = int(invite_reward["invitee_points"]) if has_invite_code else 0
            user = auth.register(
                payload.username,
                payload.password,
                email,
                invite_code=payload.invite_code,
                inviter_bonus=inviter_bonus,
                invitee_bonus=invitee_bonus,
                initial_points=platform.get_default_user_points(),
            )
            if verification is not None and email_code_record is not None:
                verification.consume_code(email_code_record.code_id)
            if has_invite_code and user.get("invited_by"):
                wallet_service = get_wallet_service(request)
                inviter = auth.get_user(str(user["invited_by"]))
                now_ts = time.time()
                wallet_orders: list[WalletOrderRecord] = []
                if inviter and inviter_bonus > 0:
                    wallet_orders.append(
                        WalletOrderRecord(
                            order_id=secrets.token_hex(12),
                            user_id=str(inviter["user_id"]),
                            username=str(inviter["username"]),
                            kind="points",
                            points_delta=inviter_bonus,
                            days_delta=0,
                            source="invite_bonus",
                            source_id=str(user["user_id"]),
                            status="completed",
                            created_by=str(user["username"]),
                            created_at=now_ts,
                        )
                    )
                if invitee_bonus > 0:
                    wallet_orders.append(
                        WalletOrderRecord(
                            order_id=secrets.token_hex(12),
                            user_id=str(user["user_id"]),
                            username=str(user["username"]),
                            kind="points",
                            points_delta=invitee_bonus,
                            days_delta=0,
                            source="invite_bonus",
                            source_id=str(inviter["user_id"]) if inviter else None,
                            status="completed",
                            created_by=str(inviter["username"]) if inviter else "system",
                            created_at=now_ts,
                        )
                    )
                if wallet_orders:
                    try:
                        wallet_service.record_wallet_orders(wallet_orders)
                    except Exception as exc:
                        # 注册与余额变更已经由 AuthService 完成，审计流水失败不能回滚已提交的注册。
                        log_event(
                            "invite_reward_audit_failed",
                            {
                                "user_id": str(user["user_id"]),
                                "order_count": len(wallet_orders),
                                "error_type": type(exc).__name__,
                            },
                        )
                if inviter:
                    notification_service.try_create_notification(
                        user_id=str(inviter["user_id"]),
                        level="success",
                        category="wallet",
                        title="邀请好友成功奖励通知",
                        content=(
                            f"用户【{user['username']}】已通过您的邀请码成功注册。"
                            + (f" 奖励积分 {inviter_bonus} 点已到账。" if inviter_bonus > 0 else "")
                        ),
                    )
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
        registration_config_enabled = platform.is_registration_enabled()
        first_user_allowed = not auth.has_users()
        sys_config = platform.get_system_config()
        return JSONResponse(
            {
                "ok": True,
                "registration_enabled": registration_config_enabled or first_user_allowed,
                "config_enabled": registration_config_enabled,
                "first_user_allowed": first_user_allowed,
                "email_registration_mode": platform.get_registration_email_mode(),
                "email_verification_enabled": platform.is_email_verification_enabled(),
                "email_required": platform.is_registration_email_required(),
                "registration_captcha_enabled": is_config_enabled(
                    sys_config, "registration_captcha_enabled", default=False
                ),
                "login_captcha_enabled": is_config_enabled(
                    sys_config, "login_captcha_enabled", default=True
                ),
                "login_failure_threshold": login_failure_threshold(sys_config),
            }
        )

    @router.post("/auth/login")
    def login(
        request: Request,
        payload: LoginPayload = Body(default_factory=LoginPayload),
    ) -> JSONResponse:
        auth = get_auth_service(request)
        platform = get_settings_service(request)
        current_client_ip = client_ip(request)
        login_id = (payload.username or "").strip()
        throttle_key = f"{login_id}\n{current_client_ip}"
        fail_count = auth.get_failure_count(throttle_key)

        sys_config = platform.get_system_config()
        login_captcha_enabled = is_config_enabled(
            sys_config, "login_captcha_enabled", default=True
        )
        threshold = login_failure_threshold(sys_config)

        require_captcha = login_captcha_enabled and fail_count >= threshold
        captcha_token_str = payload.get_clean_captcha_token()
        if require_captcha:
            if not captcha_token_str:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": {"code": "CAPTCHA_REQUIRED", "message": "登录失败次数过多，请输入滑块验证码"},
                        "require_captcha": True,
                        "fail_count": fail_count,
                    },
                    status_code=400,
                )
            slider_service = get_slider_captcha_service(request)
            if not slider_service.consume_token(
                captcha_token_str, client_ip=current_client_ip
            ):
                return JSONResponse(
                    {
                        "ok": False,
                        "error": {"code": "CAPTCHA_INVALID", "message": "滑块验证已失效或超时，请重新滑动"},
                        "require_captcha": True,
                        "fail_count": fail_count,
                    },
                    status_code=400,
                )

        try:
            token, user, ttl = auth.login(
                payload.username,
                payload.password,
                remember=payload.remember,
                client_ip=current_client_ip,
            )
        except AuthError as exc:
            new_fail_count = auth.get_failure_count(throttle_key)
            new_require_captcha = login_captcha_enabled and new_fail_count >= threshold
            data = {
                "ok": False,
                "error": {"code": exc.code, "message": exc.message},
                "require_captcha": new_require_captcha,
                "fail_count": new_fail_count,
            }
            return JSONResponse(data, status_code=exc.http_status)

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
