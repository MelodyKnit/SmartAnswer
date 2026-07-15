"""本地账号鉴权服务。"""

from __future__ import annotations

import hmac
import secrets
import time
from pathlib import Path
from threading import Lock

from ..storage.repositories.auth import SqlAlchemyAuthRepository
from ..storage.redis_state import build_session_store_from_env
from .records import SessionRecord, UserRecord
from .security import (
    MIN_PASSWORD_LEN,
    RESET_TOKEN_TTL,
    SALT_BYTES,
    SESSION_TTL_DEFAULT,
    SESSION_TTL_REMEMBER,
    THROTTLE_LOCK,
    THROTTLE_MAX_FAILURES,
    THROTTLE_WINDOW,
    USERNAME_RE,
    hash_password,
    hash_token,
)


class AuthError(Exception):
    """鉴权相关的业务错误。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class AuthService:
    """账号鉴权服务，负责用户、会话与重置令牌管理。"""

    def __init__(self, path: str | Path) -> None:
        """初始化鉴权服务。

        Args:
            path: 数据库路径、数据库 URL，或兼容的旧 JSON 路径。
        """
        self.path = Path(path) if not isinstance(path, Path) and "://" not in str(path) else path
        self._lock = Lock()
        self._failures: dict[str, list[float]] = {}
        self.repository = SqlAlchemyAuthRepository(path)
        self.session_store = build_session_store_from_env()

    def register(
        self,
        username: str,
        password: str,
        email: str | None = None,
        *,
        invite_code: str = "",
        invite_bonus: int = 0,
        initial_points: int = 100,
    ) -> dict:
        """注册新用户。首个注册用户自动成为 superadmin。"""
        username = (username or "").strip()
        email = (email or "").strip().lower() or None
        self.validate_username(username)
        self.validate_password(password)

        with self._lock:
            if self.repository.get_user(username) is not None:
                raise AuthError("USERNAME_TAKEN", "该用户名已被注册", http_status=409)
            if email and self.repository.get_user_by_email(email) is not None:
                raise AuthError("EMAIL_TAKEN", "该邮箱已被注册", http_status=409)
            role = "superadmin" if not self.repository.has_users() else "user"
            normalized_invite_code = (invite_code or "").strip()
            inviter = (
                self.repository.get_user_by_invite_code(normalized_invite_code)
                if normalized_invite_code
                else None
            )
            if normalized_invite_code and inviter is None:
                raise AuthError("INVALID_INVITE_CODE", "邀请码无效", http_status=400)
            bonus_points = max(0, int(invite_bonus)) if inviter else 0
            salt = secrets.token_hex(SALT_BYTES)
            user = UserRecord(
                user_id=secrets.token_hex(16),
                username=username,
                role=role,
                status="active",
                salt=salt,
                password_hash=hash_password(password, salt),
                email=email,
                points=max(0, int(initial_points)) + bonus_points,
                created_at=time.time(),
                invite_code=self.generate_unique_invite_code(),
                invited_by=inviter.username if inviter else "",
            )
            self.repository.save_user(user)
            if inviter and bonus_points:
                inviter.points = max(0, int(inviter.points) + bonus_points)
                self.repository.save_user(inviter)
            return self.public_user_dict(user)

    def assert_invite_code_valid(self, invite_code: str) -> None:
        """校验邀请码是否存在，空邀请码视为未使用邀请。"""

        normalized_invite_code = (invite_code or "").strip()
        if (
            normalized_invite_code
            and self.repository.get_user_by_invite_code(normalized_invite_code) is None
        ):
            raise AuthError("INVALID_INVITE_CODE", "邀请码无效", http_status=400)

    def login(
        self, username: str, password: str, *, remember: bool = False, client_ip: str = ""
    ) -> tuple[str, dict, int]:
        """校验用户名或邮箱与密码并签发会话令牌。"""
        login_id = (username or "").strip()
        throttle_key = f"{login_id}\n{client_ip}"
        with self._lock:
            self.assert_not_locked(throttle_key)
            user = self.repository.get_user_by_login(login_id)
            if user is not None and user.status != "active":
                raise AuthError("ACCOUNT_DISABLED", "账号已被禁用", http_status=403)
            ok = user is not None and hmac.compare_digest(
                user.password_hash, hash_password(password, user.salt)
            )
            if not user or not ok:
                self.record_failure(throttle_key)
                raise AuthError("BAD_CREDENTIALS", "用户名、邮箱或密码错误", http_status=401)

            self._failures.pop(throttle_key, None)
            ttl = SESSION_TTL_REMEMBER if remember else SESSION_TTL_DEFAULT
            token = secrets.token_urlsafe(32)
            self.session_store.save(
                token,
                SessionRecord(
                    username=user.username,
                    role=user.role,
                    expires_at=time.time() + ttl,
                ),
                ttl,
            )
            return token, self.public_user_dict(user), ttl

    def resolve_session(self, token: str | None) -> dict | None:
        """根据会话令牌解析当前用户。"""
        if not token:
            return None
        session = self.session_store.read(token)
        if session is None:
            return None
        if session.expires_at < time.time():
            self.session_store.delete(token)
            return None
        user = self.repository.get_user(session.username)
        if user is None or user.status != "active":
            self.session_store.delete(token)
            return None
        return self.public_user_dict(user)

    def logout(self, token: str | None) -> None:
        """注销指定会话令牌。"""
        if not token:
            return
        self.session_store.delete(token)

    def has_users(self) -> bool:
        """判断系统中是否已经存在账号。"""
        return self.repository.has_users()

    def get_user(self, username: str) -> dict | None:
        """按用户名读取单个用户的公开信息。"""
        user = self.repository.get_user((username or "").strip())
        return self.public_user_dict(user) if user else None

    def list_users(self) -> list[dict]:
        """返回全部用户的公开信息列表。"""
        return [self.public_user_dict(user) for user in self.repository.list_users()]

    def resolve_user_by_id(self, user_id: str | None) -> dict | None:
        """按用户 ID 解析当前仍处于激活状态的用户。"""
        if not user_id:
            return None
        user = self.repository.get_user_by_id(user_id)
        if user is None or user.status != "active":
            return None
        return self.public_user_dict(user)

    def set_role(self, username: str, role: str) -> dict:
        """更新用户角色。"""
        username = (username or "").strip()
        role = (role or "").strip().lower()
        if role not in {"superadmin", "admin", "user"}:
            raise AuthError(
                "INVALID_INPUT", "角色必须为 superadmin、admin 或 user", http_status=400
            )
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            user.role = role
            self.repository.save_user(user)
            return self.public_user_dict(user)

    def set_status(self, username: str, status: str) -> dict:
        """更新用户状态，并在禁用时吊销其全部会话。"""
        username = (username or "").strip()
        status = (status or "").strip().lower()
        if status not in {"active", "disabled"}:
            raise AuthError("INVALID_INPUT", "状态必须为 active 或 disabled", http_status=400)
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            user.status = status
            self.repository.save_user(user)
            if status != "active":
                self.session_store.delete_user_sessions(username)
            return self.public_user_dict(user)

    def set_display_name(self, username: str, display_name: str | None) -> dict:
        """更新展示名。

        当前用户表尚未独立持久化展示名；为了兼容前端资料接口，先校验用户
        存在并返回公开资料，展示名由响应中的用户名兜底。
        """
        username = (username or "").strip()
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            payload = self.public_user_dict(user)
            payload["display_name"] = (display_name or "").strip() or user.username
            return payload

    def change_password(self, username: str, old_password: str, new_password: str) -> None:
        """校验旧密码后更新当前用户密码，并吊销已有会话。"""
        username = (username or "").strip()
        if len(new_password or "") < MIN_PASSWORD_LEN:
            raise AuthError(
                "WEAK_PASSWORD", f"密码长度至少需要 {MIN_PASSWORD_LEN} 位", http_status=400
            )
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            old_hash = hash_password(old_password, user.salt)
            if not hmac.compare_digest(old_hash, user.password_hash):
                raise AuthError("INVALID_PASSWORD", "原密码不正确", http_status=400)
            salt = secrets.token_hex(16)
            user.salt = salt
            user.password_hash = hash_password(new_password, salt)
            self.repository.save_user(user)
            self.session_store.delete_user_sessions(username)

    def delete_user(self, username: str) -> bool:
        """删除用户并清理其登录会话。"""
        username = (username or "").strip()
        with self._lock:
            deleted = self.repository.delete_user(username)
            if deleted:
                self.session_store.delete_user_sessions(username)
            return deleted

    def set_points(self, username: str, points: int) -> dict:
        """直接设置用户积分余额。"""
        username = (username or "").strip()
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            user.points = max(0, int(points))
            self.repository.save_user(user)
            return self.public_user_dict(user)

    def add_points(self, username: str, points: int) -> dict:
        """按增量增加用户积分余额。"""
        username = (username or "").strip()
        points = max(0, int(points))
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            user.points = max(0, int(user.points) + points)
            self.repository.save_user(user)
            return self.public_user_dict(user)

    def consume_points(self, username: str, points: int) -> dict:
        """扣减用户积分，不足时抛出业务错误。"""
        username = (username or "").strip()
        points = max(0, int(points))
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                raise AuthError("USER_NOT_FOUND", "用户不存在", http_status=404)
            if user.points < points:
                raise AuthError("INSUFFICIENT_POINTS", "积分不足", http_status=402)
            user.points -= points
            self.repository.save_user(user)
            return self.public_user_dict(user)

    def create_reset_token(self, username: str) -> str | None:
        """生成一次性密码重置令牌。"""
        username = (username or "").strip()
        with self._lock:
            user = self.repository.get_user(username)
            if user is None:
                return None
            token = secrets.token_urlsafe(24)
            user.reset_token_hash = hash_token(token)
            user.reset_expires_at = time.time() + RESET_TOKEN_TTL
            self.repository.save_user(user)
            return token

    def confirm_reset(self, username: str, token: str, new_password: str) -> None:
        """使用重置令牌设置新密码。"""
        username = (username or "").strip()
        self.validate_password(new_password)
        with self._lock:
            user = self.repository.get_user(username)
            if (
                user is None
                or not user.reset_token_hash
                or user.reset_expires_at < time.time()
                or not hmac.compare_digest(user.reset_token_hash, hash_token(token or ""))
            ):
                raise AuthError("INVALID_RESET_TOKEN", "重置令牌无效或已过期", http_status=400)
            user.salt = secrets.token_hex(SALT_BYTES)
            user.password_hash = hash_password(new_password, user.salt)
            user.reset_token_hash = None
            user.reset_expires_at = 0.0
            self.repository.save_user(user)
            self.session_store.delete_user_sessions(username)

    def validate_username(self, username: str) -> None:
        """校验用户名格式。"""
        if not USERNAME_RE.match(username or ""):
            raise AuthError(
                "INVALID_INPUT",
                "用户名需为 3–32 位，仅可含中文、字母、数字、下划线或连字符",
                http_status=400,
            )

    def validate_password(self, password: str) -> None:
        """校验密码强度。"""
        if not password or len(password) < MIN_PASSWORD_LEN:
            raise AuthError("WEAK_PASSWORD", "密码至少需要 8 位", http_status=400)

    def assert_not_locked(self, key: str) -> None:
        """在登录前检查该账号/IP 是否仍处于节流锁定期。"""
        record = self._failures.get(key)
        if not record:
            return
        first_ts, _count, locked_until = record[0], record[1], record[2]
        now = time.time()
        if locked_until > now:
            remaining = int(locked_until - now)
            raise AuthError(
                "TOO_MANY_ATTEMPTS",
                f"登录失败过多，请在约 {remaining // 60 + 1} 分钟后重试",
                http_status=429,
            )
        if now - first_ts > THROTTLE_WINDOW:
            self._failures.pop(key, None)

    def record_failure(self, key: str) -> None:
        """记录一次登录失败，并按阈值设置锁定时间。"""
        now = time.time()
        record = self._failures.get(key)
        if not record or now - record[0] > THROTTLE_WINDOW:
            self._failures[key] = [now, 1.0, 0.0]
            return
        record[1] += 1.0
        if record[1] >= THROTTLE_MAX_FAILURES:
            record[2] = now + THROTTLE_LOCK

    def load_users(self) -> list[UserRecord]:
        """兼容旧调用，返回全部用户记录。"""
        return self.repository.list_users()

    def generate_unique_invite_code(self) -> str:
        """生成当前用户可分享的邀请码。"""

        for _ in range(16):
            code = secrets.token_hex(4)
            if self.repository.get_user_by_invite_code(code) is None:
                return code
        return secrets.token_hex(8)

    def ensure_user_invite_code(self, user: UserRecord | None) -> UserRecord | None:
        """为历史空邀请码用户补齐邀请码。"""

        if user is None or user.invite_code.strip():
            return user
        with self._lock:
            latest = self.repository.get_user(user.username)
            if latest is None:
                return user
            return self._ensure_user_invite_code_locked(latest)

    def ensure_invite_code_for_user(self, username: str) -> dict | None:
        """显式为指定用户生成缺失的邀请码，并返回公开用户信息。"""

        user = self.repository.get_user((username or "").strip())
        user = self.ensure_user_invite_code(user)
        return self.public_user_dict(user) if user else None

    def _ensure_user_invite_code_locked(self, user: UserRecord) -> UserRecord:
        """在持锁上下文中为缺失邀请码的用户生成稳定邀请码。"""

        if user.invite_code.strip():
            return user
        user.invite_code = self.generate_unique_invite_code()
        self.repository.save_user(user)
        return user

    def save_users(self) -> None:
        """兼容旧调用，无需额外操作。"""
        return None

    def public_user_dict(self, user: UserRecord) -> dict:
        """生成对外可见的用户公开信息。"""
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "status": user.status,
            "email": user.email,
            "points": user.points,
            "invite_code": user.invite_code,
            "invited_by": user.invited_by,
            "created_at": user.created_at,
        }
