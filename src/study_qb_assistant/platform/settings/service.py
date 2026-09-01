"""系统设置与计费策略服务。"""

from __future__ import annotations

from threading import RLock
from typing import Any, Literal, TypedDict, cast

from ...auth import AuthError
from ...auth.email_verification import normalize_email, smtp_settings_from_config
from ...llm.config import service as llm_config_service
from ..base import PlatformDomainService
from ..config import (
    LLM_RUNTIME_CONFIG_KEYS,
    LLM_RUNTIME_ENV_MAP,
    SYSTEM_CONFIG_BOOLEAN_KEYS,
    SYSTEM_CONFIG_DEFAULTS,
    SYSTEM_CONFIG_ENV_MAP,
    SYSTEM_CONFIG_KEYS,
    SYSTEM_CONFIG_SECRET_KEYS,
)
from .validation import normalize_email_code_policy_value, normalize_site_logo_url


InviteRewardMode = Literal["inviter", "invitee", "both"]
INVITE_REWARD_MODES = frozenset({"inviter", "invitee", "both"})


class InviteRewardPolicy(TypedDict):
    """邀请码注册时各参与方的积分发放策略。"""

    mode: InviteRewardMode
    points: int
    inviter_points: int
    invitee_points: int


class SettingsService(PlatformDomainService):
    """SettingsService 领域实现。"""

    def __init__(self, repository: Any, llm_repository: Any, lock: RLock) -> None:
        super().__init__(repository, lock)
        self.llm_repository = llm_repository

    @staticmethod
    def default_system_config() -> dict[str, str]:
        """返回平台系统配置默认值。"""

        return dict(SYSTEM_CONFIG_DEFAULTS)

    def get_billing(self) -> dict:
        """读取当前积分计费配置。"""
        with self.lock:
            defaults = {"local_hit": 1, "web_search": 2, "llm_fallback": 3}
            stored = self.repository.get_settings("billing", keys=set(defaults.keys()))
            return {key: max(0, int(stored.get(key, default))) for key, default in defaults.items()}

    def get_max_query_cost(self) -> int:
        """返回一次查题链路可能产生的最高积分消耗。"""

        return max(self.get_billing().values(), default=0)

    def get_image_generation_policy(self) -> dict[str, int]:
        """返回文本生图的积分、限流与资产保留策略。"""

        return {
            "points": self.system_points_value("image_generation_points"),
            "max_active_jobs": max(1, self.system_points_value("image_generation_max_active_jobs")),
            "daily_limit": self.system_points_value("image_generation_daily_limit"),
            "retention_days": self.system_points_value("image_generation_retention_days"),
        }

    def set_billing(self, values: dict[str, int]) -> dict:
        """更新积分计费配置。"""
        current = self.get_billing()
        for key, value in values.items():
            if key not in current:
                raise AuthError("INVALID_INPUT", f"不支持的积分项目: {key}", http_status=400)
            current[key] = max(0, int(value))
        with self.lock:
            self.repository.replace_settings(
                "billing", {key: str(value) for key, value in current.items()}
            )
        return current

    def calculate_points_cost(self, resolution_mode: str) -> int:
        """根据查题命中方式计算本次调用的积分消耗。"""
        mode = str(resolution_mode or "").strip()
        if mode in {"input_anomaly", "not_found", "model_error", "invalid_request", ""}:
            return 0
        billing = self.get_billing()
        if mode == "llm_fallback":
            return billing["llm_fallback"]
        if mode in {"exact_match", "fuzzy_match", "known_rule", "ai_cache"}:
            return billing["local_hit"]
        if mode == "web_search":
            return billing["web_search"]
        return 0

    def system_points_value(self, key: str) -> int:
        """读取非负整数型积分策略配置。"""

        if key not in SYSTEM_CONFIG_KEYS:
            raise AuthError("INVALID_INPUT", f"不支持的系统配置项: {key}", http_status=400)
        raw = self.repository.get_settings("system_config", keys={key})
        value = raw.get(key, SYSTEM_CONFIG_DEFAULTS.get(key, "0"))
        try:
            return max(0, int(str(value or "0").strip() or "0"))
        except ValueError as exc:
            raise AuthError("INVALID_INPUT", f"{key} 必须为非负整数", http_status=400) from exc

    def get_default_user_points(self) -> int:
        """返回新注册用户初始积分。"""

        return self.system_points_value("default_user_points")

    def get_invite_bonus(self) -> int:
        """返回注册邀请码奖励积分。"""

        return self.system_points_value("invite_bonus_points")

    def get_invite_reward_mode(self) -> InviteRewardMode:
        """读取邀请码奖励对象，旧配置默认兼容为双方奖励。"""

        raw = self.repository.get_settings(
            "system_config", keys={"invite_reward_mode"}
        ).get("invite_reward_mode", SYSTEM_CONFIG_DEFAULTS["invite_reward_mode"])
        mode = str(raw or "").strip().lower()
        if mode in INVITE_REWARD_MODES:
            return cast(InviteRewardMode, mode)
        return "both"

    def get_invite_reward_policy(self) -> InviteRewardPolicy:
        """返回当前邀请码奖励规则及邀请双方各自可获得的积分。"""

        mode = self.get_invite_reward_mode()
        points = self.get_invite_bonus()
        return {
            "mode": mode,
            "points": points,
            "inviter_points": points if mode in {"inviter", "both"} else 0,
            "invitee_points": points if mode in {"invitee", "both"} else 0,
        }

    def is_registration_enabled(self) -> bool:
        """返回公开注册入口是否启用。"""

        raw = self.get_system_config().get("registration_enabled", "true")
        return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}

    def is_email_verification_enabled(self) -> bool:
        """返回注册邮箱验证是否启用。"""

        return self.get_registration_email_mode() == "verified"

    def is_registration_email_required(self) -> bool:
        """返回注册时是否必须提供邮箱。"""

        return self.get_registration_email_mode() in {"required", "verified"}

    def get_registration_email_mode(self) -> str:
        """读取注册邮箱策略，并兼容旧版布尔验证码配置。"""

        raw = self.repository.get_settings("system_config", keys={"registration_email_mode"})
        configured_mode = str(raw.get("registration_email_mode") or "").strip().lower()
        if configured_mode in {"optional", "required", "verified"}:
            return configured_mode

        legacy = self.repository.get_settings(
            "system_config", keys={"email_verification_enabled"}
        ).get("email_verification_enabled", "false")
        return (
            "verified"
            if str(legacy).strip().lower() not in {"0", "false", "no", "off", "disabled"}
            else "optional"
        )

    def get_points_policy(self) -> dict[str, int | InviteRewardMode]:
        """返回前端表单需要展示或预填的积分策略。"""

        return {
            "default_user_points": self.get_default_user_points(),
            "invite_bonus_points": self.get_invite_bonus(),
            "invite_reward_mode": self.get_invite_reward_mode(),
            "manual_grant_default_points": self.system_points_value(
                "manual_grant_default_points"
            ),
            "redeem_code_default_points": self.system_points_value(
                "redeem_code_default_points"
            ),
        }

    def get_system_config(self, *, reveal_secret: bool = False) -> dict:
        """读取系统运行配置；默认对敏感项只暴露是否已配置。"""
        with self.lock:
            raw = {key: SYSTEM_CONFIG_DEFAULTS.get(key, "") for key in SYSTEM_CONFIG_KEYS}
            raw.update(self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS)))
            payload: dict[str, str | bool] = {}
            for key, value in raw.items():
                if key in SYSTEM_CONFIG_SECRET_KEYS and not reveal_secret:
                    payload[f"{key}_configured"] = bool(str(value).strip())
                else:
                    payload[key] = value
            email_mode = self.get_registration_email_mode()
            payload["registration_email_mode"] = email_mode
            payload["email_verification_enabled"] = "true" if email_mode == "verified" else "false"
            return payload

    def get_site_config(self) -> dict[str, object]:
        """读取可公开暴露给登录页和前端初始化使用的站点品牌配置。"""

        config = self.get_system_config()
        title = str(config.get("site_title") or SYSTEM_CONFIG_DEFAULTS["site_title"]).strip()
        raw_logo_url = str(config.get("site_logo_url") or "").strip()
        try:
            logo_url = normalize_site_logo_url(raw_logo_url)
        except AuthError:
            logo_url = ""

        site_logo_urls: dict[str, str] = {}
        if logo_url.startswith("/media/brand/"):
            import re

            match = re.match(r"^/media/brand/logo_([a-z]+)\.png(\?t=\d+)?$", logo_url)
            if match:
                t_suffix = match.group(2) or ""
                for size_key in ("original", "lg", "md", "sm"):
                    site_logo_urls[size_key] = f"/media/brand/logo_{size_key}.png{t_suffix}"

        if not site_logo_urls:
            for size_key in ("original", "lg", "md", "sm"):
                site_logo_urls[size_key] = logo_url

        return {
            "site_title": title or SYSTEM_CONFIG_DEFAULTS["site_title"],
            "site_logo_url": logo_url,
            "site_logo_urls": site_logo_urls,
        }

    def get_llm_runtime_config(self, *, reveal_secret: bool = False) -> dict:
        """读取统一后的 LLM 答题运行时配置。"""

        llm_config_service.migrate_legacy_llm_settings(
            self.llm_repository,
            default_system_config=self.default_system_config(),
        )
        return llm_config_service.get_llm_runtime_config(
            self.llm_repository,
            self.lock,
            reveal_secret=reveal_secret,
        )

    def set_llm_runtime_config(self, values: dict[str, object]) -> dict:
        """更新统一后的 LLM 答题运行时配置。"""

        llm_config_service.migrate_legacy_llm_settings(
            self.llm_repository,
            default_system_config=self.default_system_config(),
        )
        return llm_config_service.set_llm_runtime_config(
            self.llm_repository,
            self.lock,
            values,
        )

    def llm_runtime_env(self) -> dict[str, str]:
        """把统一后的 LLM 答题配置转换为环境变量。"""

        raw = self.llm_repository.get_settings(
            "llm_runtime_config",
            keys=set(LLM_RUNTIME_CONFIG_KEYS),
        )
        return {
            env_key: str(raw.get(config_key) or "").strip()
            for config_key, env_key in LLM_RUNTIME_ENV_MAP.items()
            if str(raw.get(config_key) or "").strip()
        }

    def set_system_config(self, values: dict[str, object]) -> dict:
        """更新系统运行配置。"""
        normalized: dict[str, str] = {}
        for key, value in values.items():
            if key not in SYSTEM_CONFIG_KEYS:
                raise AuthError("INVALID_INPUT", f"不支持的系统配置项: {key}", http_status=400)
            text = "" if value is None else str(value).strip()
            if key in SYSTEM_CONFIG_SECRET_KEYS and not text:
                continue
            if key == "site_title":
                text = text or SYSTEM_CONFIG_DEFAULTS["site_title"]
                if len(text) > 40:
                    raise AuthError("INVALID_INPUT", "网站标题不能超过 40 个字符", http_status=400)
            elif key == "site_logo_url":
                text = normalize_site_logo_url(text)
            elif key == "smtp_security":
                text = text.lower() or SYSTEM_CONFIG_DEFAULTS["smtp_security"]
                if text not in {"ssl", "starttls", "none"}:
                    raise AuthError(
                        "INVALID_INPUT", "SMTP 加密方式必须为 ssl、starttls 或 none", http_status=400
                    )
            elif key == "smtp_port":
                try:
                    parsed_port = int(text or SYSTEM_CONFIG_DEFAULTS["smtp_port"])
                except ValueError as exc:
                    raise AuthError("INVALID_INPUT", "SMTP 端口必须为有效整数", http_status=400) from exc
                if parsed_port < 1 or parsed_port > 65535:
                    raise AuthError("INVALID_INPUT", "SMTP 端口必须在 1 到 65535 之间", http_status=400)
                text = str(parsed_port)
            elif key in {
                "email_code_ttl_minutes",
                "email_code_cooldown_seconds",
                "email_code_daily_limit",
                "email_code_ip_hourly_limit",
                "email_code_max_attempts",
            }:
                text = normalize_email_code_policy_value(key, text)
            elif key == "smtp_from_email" and text:
                text = normalize_email(text)
            elif key == "smtp_from_name":
                text = text or SYSTEM_CONFIG_DEFAULTS["smtp_from_name"]
                if any(ch in text for ch in "\r\n"):
                    raise AuthError("INVALID_INPUT", "发件人名称格式不正确", http_status=400)
                if len(text) > 40:
                    raise AuthError("INVALID_INPUT", "发件人名称不能超过 40 个字符", http_status=400)
            elif key == "registration_email_mode":
                text = text.lower() or "optional"
                if text not in {"optional", "required", "verified"}:
                    raise AuthError(
                        "INVALID_INPUT",
                        "注册邮箱策略必须为 optional、required 或 verified",
                        http_status=400,
                    )
            elif key == "invite_reward_mode":
                text = text.lower() or SYSTEM_CONFIG_DEFAULTS["invite_reward_mode"]
                if text not in INVITE_REWARD_MODES:
                    raise AuthError(
                        "INVALID_INPUT",
                        "邀请码奖励对象必须为 inviter、invitee 或 both",
                        http_status=400,
                    )
            elif key in SYSTEM_CONFIG_BOOLEAN_KEYS:
                text = (
                    "false" if text.lower() in {"0", "false", "no", "off", "disabled"} else "true"
                )
            elif key.endswith("_points") or key in {
                "answer_retry_times",
                "image_generation_max_active_jobs",
                "image_generation_daily_limit",
                "image_generation_retention_days",
            }:
                try:
                    parsed = max(0, int(text or "0"))
                except ValueError as exc:
                    raise AuthError(
                        "INVALID_INPUT", f"{key} 必须为非负整数", http_status=400
                    ) from exc
                if key == "answer_retry_times":
                    parsed = min(parsed, 10)
                elif key == "image_generation_max_active_jobs":
                    if parsed < 1 or parsed > 10:
                        raise AuthError(
                            "INVALID_INPUT", "单用户活动生图任务数必须在 1 到 10 之间", http_status=400
                        )
                elif key == "image_generation_daily_limit":
                    if parsed > 1000:
                        raise AuthError(
                            "INVALID_INPUT", "每日生图上限不能超过 1000", http_status=400
                        )
                elif key == "image_generation_retention_days" and parsed > 3650:
                    raise AuthError(
                        "INVALID_INPUT", "生图保留天数不能超过 3650", http_status=400
                    )
                text = str(parsed)
            normalized[key] = text
        with self.lock:
            stored = self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS))
            current = {key: SYSTEM_CONFIG_DEFAULTS.get(key, "") for key in SYSTEM_CONFIG_KEYS}
            current.update(stored)
            candidate = {**current, **normalized}
            if "registration_email_mode" in normalized:
                candidate_mode = normalized["registration_email_mode"]
            elif "registration_email_mode" in stored:
                candidate_mode = str(stored["registration_email_mode"]).lower()
            else:
                candidate_mode = (
                    "verified"
                    if str(candidate.get("email_verification_enabled") or "").lower() == "true"
                    else "optional"
                )
            if candidate_mode == "verified":
                host = str(candidate.get("smtp_host") or "").strip()
                from_email = str(candidate.get("smtp_from_email") or "").strip()
                username = str(candidate.get("smtp_username") or "").strip()
                password = str(candidate.get("smtp_password") or "").strip()

                if not host or not from_email or not username:
                    raise AuthError("INVALID_INPUT", "启用的邮箱验证码注册前，请先完整配置 SMTP 服务（宿主机、用户名与发件邮箱）", http_status=400)

                is_pwd_configured = bool(current.get("smtp_password_configured")) or bool(current.get("smtp_password"))
                if not password and not is_pwd_configured:
                    raise AuthError("INVALID_INPUT", "启用的邮箱验证码注册前，请先输入 SMTP 密码", http_status=400)

                smtp_settings_from_config(candidate)
            self.repository.set_settings("system_config", normalized)
        return self.get_system_config()

    def clear_system_secret(self, key: str) -> dict:
        """清除一个可写入但不会回显的系统敏感配置。"""

        if key not in SYSTEM_CONFIG_SECRET_KEYS:
            raise AuthError("INVALID_INPUT", f"不是可清除的敏感配置: {key}", http_status=400)
        with self.lock:
            self.repository.set_settings("system_config", {key: ""})
        return self.get_system_config()

    def runtime_env(self) -> dict[str, str]:
        """把平台配置转换为运行时环境变量映射。"""
        raw = self.repository.get_settings("system_config", keys=set(SYSTEM_CONFIG_KEYS))
        env = {
            env_key: str(raw.get(config_key) or "").strip()
            for config_key, env_key in SYSTEM_CONFIG_ENV_MAP.items()
            if str(raw.get(config_key) or "").strip()
        }
        env.update(self.llm_runtime_env())
        return env
