"""邮箱验证码注册服务。"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from ..config import get_global_config
from ..logger import log_event
from .records import EmailVerificationCodeRecord
from .security import hash_token
from .service import AuthError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SUPPORTED_PURPOSES = {"register"}


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    """SMTP 发信配置。"""

    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str


class EmailSender(Protocol):
    """邮箱发送器协议，便于测试注入 fake sender。"""

    def send_verification_code(
        self,
        *,
        settings: SmtpSettings,
        to_email: str,
        code: str,
        ttl_minutes: int,
    ) -> None:
        """发送注册验证码。"""


class SmtpEmailSender:
    """基于 Python 标准库 smtplib 的 SMTP 发送器。"""

    def send_verification_code(
        self,
        *,
        settings: SmtpSettings,
        to_email: str,
        code: str,
        ttl_minutes: int,
    ) -> None:
        message = EmailMessage()
        from_name = settings.from_name or "AI题库"
        message["Subject"] = "AI题库注册验证码"
        message["From"] = f"{from_name} <{settings.from_email}>"
        message["To"] = to_email
        message.set_content(
            "\n".join(
                [
                    "您好，",
                    "",
                    f"您正在注册 AI题库，验证码为：{code}",
                    f"验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。",
                    "",
                    "如果这不是您本人操作，请忽略本邮件。",
                ]
            )
        )

        security = settings.security.lower()
        if security == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.host, settings.port, context=context, timeout=15
            ) as smtp:
                self._login_if_needed(smtp, settings)
                smtp.send_message(message)
            return

        with smtplib.SMTP(settings.host, settings.port, timeout=15) as smtp:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            self._login_if_needed(smtp, settings)
            smtp.send_message(message)

    def _login_if_needed(self, smtp: smtplib.SMTP, settings: SmtpSettings) -> None:
        if settings.username:
            smtp.login(settings.username, settings.password)


class EmailDomainWhitelist:
    """按 mtime 缓存的邮箱域名白名单。"""

    def __init__(self, path: Path | None = None) -> None:
        if path is not None:
            self.path = path
        else:
            config = get_global_config()
            self.path = config.email_domain_whitelist_path_resolved
            seed_runtime_whitelist(
                source=config.config_dir / "email-domain-whitelist.json",
                target=self.path,
            )
        self._mtime: float | None = None
        self._domains: set[str] = set()

    def domains(self) -> set[str]:
        """读取当前白名单域名集合，文件修改后自动刷新。"""

        try:
            stat = self.path.stat()
        except FileNotFoundError as exc:
            log_event("email_domain_whitelist_error", {"error": "file_not_found"})
            raise AuthError(
                "EMAIL_DOMAIN_NOT_ALLOWED", "邮箱域名白名单不可用", http_status=400
            ) from exc
        if self._mtime == stat.st_mtime:
            return set(self._domains)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            domains = payload.get("domains")
            if not isinstance(domains, list):
                raise ValueError("domains must be a list")
            parsed = {
                str(item).strip().lower()
                for item in domains
                if str(item).strip() and "@" not in str(item)
            }
        except Exception as exc:
            log_event("email_domain_whitelist_error", {"error": str(exc)})
            raise AuthError(
                "EMAIL_DOMAIN_NOT_ALLOWED", "邮箱域名白名单格式错误", http_status=400
            ) from exc
        if not parsed:
            log_event("email_domain_whitelist_error", {"error": "empty_domains"})
            raise AuthError(
                "EMAIL_DOMAIN_NOT_ALLOWED", "邮箱域名白名单为空", http_status=400
            )
        self._mtime = stat.st_mtime
        self._domains = parsed
        return set(parsed)

    def assert_allowed(self, email: str) -> None:
        """校验邮箱域名是否在白名单内。"""

        domain = email_domain(email)
        if not domain or domain not in self.domains():
            raise AuthError(
                "EMAIL_DOMAIN_NOT_ALLOWED", "该邮箱域名暂不允许注册", http_status=400
            )


def seed_runtime_whitelist(*, source: Path, target: Path) -> None:
    """首次启动时把内置白名单复制到运行数据目录。

    使用独占创建保证并发启动不会覆盖管理员已经修改的运行时文件。
    """

    if target.exists():
        return
    try:
        content = source.read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
    except FileExistsError:
        return
    except OSError as exc:
        log_event(
            "email_domain_whitelist_seed_failed",
            {"error": str(exc), "target": str(target)},
        )


class EmailVerificationService:
    """邮箱验证码发送与校验服务。"""

    def __init__(
        self,
        repository,
        *,
        config: dict,
        sender: EmailSender | None = None,
        whitelist: EmailDomainWhitelist | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.sender = sender or SmtpEmailSender()
        self.whitelist = whitelist or EmailDomainWhitelist()

    def send_code(self, *, email: str, purpose: str, client_ip: str) -> int:
        """发送验证码，包含域名白名单与限流校验。"""

        if not config_bool(
            self.config.get("email_verification_enabled"), default=False
        ):
            raise AuthError(
                "EMAIL_VERIFICATION_DISABLED", "邮箱验证未开启", http_status=400
            )
        normalized_email = normalize_email(email)
        normalized_purpose = normalize_purpose(purpose)
        self.whitelist.assert_allowed(normalized_email)
        now = time.time()
        ip_hash = hash_client_ip(client_ip)
        ttl_minutes = config_int(
            self.config, "email_code_ttl_minutes", 10, minimum=1, maximum=60
        )
        cooldown = config_int(
            self.config, "email_code_cooldown_seconds", 60, minimum=0, maximum=3600
        )
        daily_limit = config_int(
            self.config, "email_code_daily_limit", 5, minimum=1, maximum=100
        )
        ip_hourly_limit = config_int(
            self.config, "email_code_ip_hourly_limit", 20, minimum=1, maximum=500
        )

        latest_send = self.repository.latest_email_verification_send(
            email=normalized_email,
            purpose=normalized_purpose,
        )
        if latest_send and now - latest_send.created_at < cooldown:
            raise AuthError(
                "EMAIL_CODE_RATE_LIMITED",
                "验证码发送过于频繁，请稍后再试",
                http_status=429,
            )
        if (
            self.repository.count_email_verification_sends(
                email=normalized_email,
                purpose=normalized_purpose,
                since=now - 24 * 3600,
            )
            >= daily_limit
        ):
            raise AuthError(
                "EMAIL_CODE_RATE_LIMITED",
                "该邮箱今日验证码发送次数已达上限",
                http_status=429,
            )
        if (
            self.repository.count_email_verification_sends_by_ip(
                send_ip_hash=ip_hash,
                purpose=normalized_purpose,
                since=now - 3600,
            )
            >= ip_hourly_limit
        ):
            raise AuthError(
                "EMAIL_CODE_RATE_LIMITED", "当前网络验证码发送过于频繁", http_status=429
            )

        settings = smtp_settings_from_config(self.config)
        code = generate_code()
        try:
            self.sender.send_verification_code(
                settings=settings,
                to_email=normalized_email,
                code=code,
                ttl_minutes=ttl_minutes,
            )
        except Exception as exc:
            failed_record = EmailVerificationCodeRecord(
                code_id=secrets.token_hex(12),
                email=normalized_email,
                purpose=normalized_purpose,
                code_hash=hash_token("failed:" + secrets.token_urlsafe(32)),
                expires_at=now,
                attempts=0,
                send_ip_hash=ip_hash,
                created_at=now,
                consumed_at=now,
            )
            self.repository.save_email_verification_code(failed_record)
            log_event(
                "email_verification_send_failed",
                {"email_domain": email_domain(normalized_email), "error": str(exc)},
            )
            raise AuthError(
                "EMAIL_SEND_FAILED", "验证码发送失败，请稍后再试", http_status=502
            ) from exc

        record = EmailVerificationCodeRecord(
            code_id=secrets.token_hex(12),
            email=normalized_email,
            purpose=normalized_purpose,
            code_hash=hash_token(code),
            expires_at=now + ttl_minutes * 60,
            attempts=0,
            send_ip_hash=ip_hash,
            created_at=now,
        )
        self.repository.save_email_verification_code(record)
        return cooldown

    def verify(
        self, *, email: str, purpose: str, code: str
    ) -> EmailVerificationCodeRecord | None:
        """校验验证码；成功时返回记录，由调用方在业务成功后消费。"""

        if not config_bool(
            self.config.get("email_verification_enabled"), default=False
        ):
            return None
        normalized_email = normalize_email(email)
        normalized_purpose = normalize_purpose(purpose)
        self.whitelist.assert_allowed(normalized_email)
        normalized_code = normalize_code(code)
        record = self.repository.latest_email_verification_code(
            email=normalized_email,
            purpose=normalized_purpose,
        )
        if record is None:
            raise AuthError("EMAIL_CODE_INVALID", "验证码无效或已过期", http_status=400)

        now = time.time()
        max_attempts = config_int(
            self.config, "email_code_max_attempts", 5, minimum=1, maximum=20
        )
        if record.expires_at < now:
            self.repository.consume_email_verification_code(record.code_id, now)
            raise AuthError(
                "EMAIL_CODE_EXPIRED", "验证码已过期，请重新获取", http_status=400
            )
        if record.attempts >= max_attempts:
            self.repository.consume_email_verification_code(record.code_id, now)
            raise AuthError(
                "EMAIL_CODE_INVALID", "验证码错误次数过多，请重新获取", http_status=400
            )
        if not secrets.compare_digest(record.code_hash, hash_token(normalized_code)):
            updated = self.repository.increment_email_verification_attempts(
                record.code_id
            )
            if updated.attempts >= max_attempts:
                self.repository.consume_email_verification_code(record.code_id, now)
            raise AuthError("EMAIL_CODE_INVALID", "验证码不正确", http_status=400)
        return record

    def consume_code(self, code_id: str) -> None:
        """消费已完成业务校验的验证码。"""

        self.repository.consume_email_verification_code(code_id, time.time())

    def verify_and_consume(self, *, email: str, purpose: str, code: str) -> None:
        """校验验证码并消费，保留给需要一次性操作的调用方。"""

        record = self.verify(email=email, purpose=purpose, code=code)
        if record is not None:
            self.consume_code(record.code_id)


def normalize_email(value: str | None) -> str:
    """归一化并校验邮箱格式。"""

    email = (value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("INVALID_INPUT", "邮箱格式不正确", http_status=400)
    return email


def email_domain(value: str | None) -> str:
    """提取邮箱域名。"""

    text = (value or "").strip().lower()
    if "@" not in text:
        return ""
    return text.rsplit("@", 1)[1]


def normalize_purpose(value: str | None) -> str:
    """校验验证码用途。"""

    purpose = (value or "register").strip().lower()
    if purpose not in SUPPORTED_PURPOSES:
        raise AuthError("INVALID_INPUT", "验证码用途不受支持", http_status=400)
    return purpose


def normalize_code(value: str | None) -> str:
    """校验验证码格式。"""

    code = (value or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise AuthError("EMAIL_CODE_INVALID", "验证码不正确", http_status=400)
    return code


def generate_code() -> str:
    """生成 6 位数字验证码。"""

    return f"{secrets.randbelow(1_000_000):06d}"


def hash_client_ip(value: str | None) -> str:
    """对客户端 IP 做不可逆哈希，避免明文 IP 落库。"""

    return hashlib.sha256((value or "").strip().encode("utf-8")).hexdigest()


def config_bool(value: object, *, default: bool) -> bool:
    """按系统配置常用布尔语义解析。"""

    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def config_int(
    config: dict,
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """读取带上下界的整数配置。"""

    try:
        value = int(str(config.get(key, default)).strip() or default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def smtp_settings_from_config(config: dict) -> SmtpSettings:
    """从系统配置构建 SMTP 设置。"""

    host = str(config.get("smtp_host") or "").strip()
    from_email = str(config.get("smtp_from_email") or "").strip()
    username = str(config.get("smtp_username") or "").strip()
    password = str(config.get("smtp_password") or "").strip()
    if not host or not from_email or not username or not password:
        raise AuthError("INVALID_INPUT", "请先完整配置 SMTP 服务", http_status=400)
    try:
        port = int(str(config.get("smtp_port") or "465").strip())
    except ValueError as exc:
        raise AuthError(
            "INVALID_INPUT", "SMTP 端口必须为有效整数", http_status=400
        ) from exc
    if port < 1 or port > 65535:
        raise AuthError(
            "INVALID_INPUT", "SMTP 端口必须在 1 到 65535 之间", http_status=400
        )
    security = str(config.get("smtp_security") or "ssl").strip().lower()
    if security not in {"ssl", "starttls", "none"}:
        raise AuthError(
            "INVALID_INPUT",
            "SMTP 加密方式必须为 ssl、starttls 或 none",
            http_status=400,
        )
    normalize_email(from_email)
    from_name = str(config.get("smtp_from_name") or "AI题库").strip() or "AI题库"
    if any(ch in from_name for ch in "\r\n"):
        raise AuthError("INVALID_INPUT", "发件人名称格式不正确", http_status=400)
    return SmtpSettings(
        host=host,
        port=port,
        security=security,
        username=username,
        password=password,
        from_email=from_email,
        from_name=from_name,
    )
