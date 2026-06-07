"""本地账号鉴权服务：用户存储、密码哈希、会话与重置令牌。

仅使用 Python 标准库实现。密码使用 PBKDF2-HMAC-SHA256（随机 salt + 高迭代次数）哈希，
绝不明文存储。会话令牌与忘记密码令牌使用 secrets 生成。

用户数据持久化到 JSON 文件（默认 data/runtime/users.json），采用与 ai_answer_cache 一致的
原子写（先写 .tmp 再 replace）+ 线程锁，避免并发写损坏。该文件已被 .gitignore 排除。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

# PBKDF2 参数：迭代次数足够高以抵抗离线爆破；salt 16 字节随机。
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16

# 用户名与密码规则
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-一-龥]{3,32}$")
_MIN_PASSWORD_LEN = 8

# 会话与重置令牌有效期（秒）
_SESSION_TTL_DEFAULT = 12 * 3600          # 普通登录 12 小时
_SESSION_TTL_REMEMBER = 30 * 24 * 3600    # 勾选“记住我” 30 天
_RESET_TOKEN_TTL = 30 * 60                # 重置令牌 30 分钟

# 登录失败节流：同一 (用户名,IP) 在窗口内失败超过阈值则暂时锁定
_THROTTLE_MAX_FAILURES = 5
_THROTTLE_WINDOW = 5 * 60                 # 5 分钟窗口
_THROTTLE_LOCK = 10 * 60                  # 触发后锁定 10 分钟


class AuthError(Exception):
    """鉴权相关的业务错误，携带稳定的错误码与中文消息。

    Attributes:
        code: 稳定的机器可读错误码（如 USERNAME_TAKEN）。
        message: 面向用户的中文错误说明。
        http_status: 建议的 HTTP 状态码。
    """

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(slots=True)
class _User:
    """单个用户的持久化记录。"""

    username: str
    role: str
    salt: str            # hex
    password_hash: str   # hex
    email: str | None
    created_at: float
    reset_token_hash: str | None = None
    reset_expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "role": self.role,
            "salt": self.salt,
            "password_hash": self.password_hash,
            "email": self.email,
            "created_at": self.created_at,
            "reset_token_hash": self.reset_token_hash,
            "reset_expires_at": self.reset_expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "_User":
        return cls(
            username=str(payload["username"]),
            role=str(payload.get("role") or "user"),
            salt=str(payload["salt"]),
            password_hash=str(payload["password_hash"]),
            email=(str(payload["email"]) if payload.get("email") else None),
            created_at=float(payload.get("created_at") or time.time()),
            reset_token_hash=(str(payload["reset_token_hash"]) if payload.get("reset_token_hash") else None),
            reset_expires_at=float(payload.get("reset_expires_at") or 0.0),
        )


@dataclass(slots=True)
class _Session:
    """内存会话记录。"""

    username: str
    role: str
    expires_at: float


def _hash_password(password: str, salt_hex: str) -> str:
    """用 PBKDF2-HMAC-SHA256 计算密码哈希，返回 hex 字符串。"""
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO,
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        _PBKDF2_ITERATIONS,
    )
    return derived.hex()


def _hash_token(token: str) -> str:
    """对令牌做 SHA-256 摘要后再持久化，避免明文令牌落盘。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """账号鉴权服务，管理用户、会话与忘记密码令牌。

    线程安全：所有读写共享状态的操作都在锁内进行。
    """

    def __init__(self, path: str | Path) -> None:
        """初始化鉴权服务。

        Args:
            path: 用户数据 JSON 文件路径（如 data/runtime/users.json）。
        """
        self.path = Path(path)
        self._lock = Lock()
        self._users: dict[str, _User] = {}
        self._sessions: dict[str, _Session] = {}
        # 登录失败计数：键为 "username\nip"，值为 (首次失败时间, 失败次数, 锁定截止时间)
        self._failures: dict[str, list[float]] = {}
        self._load()

    # ---------- 公共 API ----------

    def register(self, username: str, password: str, email: str | None = None) -> dict:
        """注册新用户。首个注册用户自动成为 admin，其余为 user。

        Returns:
            dict: {"username": ..., "role": ...}

        Raises:
            AuthError: 输入非法或用户名已存在。
        """
        username = (username or "").strip()
        email = (email or "").strip() or None
        self._validate_username(username)
        self._validate_password(password)

        with self._lock:
            if username in self._users:
                raise AuthError("USERNAME_TAKEN", "该用户名已被注册", http_status=409)
            role = "admin" if not self._users else "user"
            salt = secrets.token_hex(_SALT_BYTES)
            user = _User(
                username=username,
                role=role,
                salt=salt,
                password_hash=_hash_password(password, salt),
                email=email,
                created_at=time.time(),
            )
            self._users[username] = user
            self._save()
            return {"username": user.username, "role": user.role}

    def login(self, username: str, password: str, *, remember: bool = False, client_ip: str = "") -> tuple[str, dict, int]:
        """校验凭证并签发会话令牌。

        Returns:
            (token, user_dict, ttl_seconds)

        Raises:
            AuthError: 凭证错误或触发失败节流锁定。
        """
        username = (username or "").strip()
        throttle_key = f"{username}\n{client_ip}"
        with self._lock:
            self._assert_not_locked(throttle_key)
            user = self._users.get(username)
            ok = user is not None and hmac.compare_digest(
                user.password_hash, _hash_password(password, user.salt)
            )
            if not user or not ok:
                self._record_failure(throttle_key)
                raise AuthError("BAD_CREDENTIALS", "用户名或密码错误", http_status=401)

            # 成功后清除失败计数
            self._failures.pop(throttle_key, None)
            ttl = _SESSION_TTL_REMEMBER if remember else _SESSION_TTL_DEFAULT
            token = secrets.token_urlsafe(32)
            self._sessions[token] = _Session(
                username=user.username,
                role=user.role,
                expires_at=time.time() + ttl,
            )
            return token, {"username": user.username, "role": user.role}, ttl

    def resolve_session(self, token: str | None) -> dict | None:
        """根据令牌返回当前用户信息，无效或过期返回 None。"""
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at < time.time():
                self._sessions.pop(token, None)
                return None
            return {"username": session.username, "role": session.role}

    def logout(self, token: str | None) -> None:
        """注销指定会话令牌（幂等）。"""
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def has_users(self) -> bool:
        """是否已存在任何账号（用于首启动引导注册）。"""
        with self._lock:
            return bool(self._users)

    def create_reset_token(self, username: str) -> str | None:
        """为用户生成一次性重置令牌（明文仅此一次返回，存储仅存其哈希）。

        本地离线场景：调用方负责把明文令牌打印到服务器控制台/日志，用户手动复制。
        若用户名不存在，返回 None（调用方应统一提示，避免泄露账号是否存在）。
        """
        username = (username or "").strip()
        with self._lock:
            user = self._users.get(username)
            if user is None:
                return None
            token = secrets.token_urlsafe(24)
            user.reset_token_hash = _hash_token(token)
            user.reset_expires_at = time.time() + _RESET_TOKEN_TTL
            self._save()
            return token

    def confirm_reset(self, username: str, token: str, new_password: str) -> None:
        """用重置令牌设置新密码。

        Raises:
            AuthError: 令牌无效/过期或新密码过弱。
        """
        username = (username or "").strip()
        self._validate_password(new_password)
        with self._lock:
            user = self._users.get(username)
            if (
                user is None
                or not user.reset_token_hash
                or user.reset_expires_at < time.time()
                or not hmac.compare_digest(user.reset_token_hash, _hash_token(token or ""))
            ):
                raise AuthError("INVALID_RESET_TOKEN", "重置令牌无效或已过期", http_status=400)
            user.salt = secrets.token_hex(_SALT_BYTES)
            user.password_hash = _hash_password(new_password, user.salt)
            user.reset_token_hash = None
            user.reset_expires_at = 0.0
            # 重置密码后吊销该用户所有现存会话
            self._sessions = {
                tok: sess for tok, sess in self._sessions.items() if sess.username != username
            }
            self._save()

    # ---------- 内部辅助 ----------

    def _validate_username(self, username: str) -> None:
        if not _USERNAME_RE.match(username or ""):
            raise AuthError(
                "INVALID_INPUT",
                "用户名需为 3–32 位，仅可含中文、字母、数字、下划线或连字符",
                http_status=400,
            )

    def _validate_password(self, password: str) -> None:
        if not password or len(password) < _MIN_PASSWORD_LEN:
            raise AuthError("WEAK_PASSWORD", "密码至少需要 8 位", http_status=400)

    def _assert_not_locked(self, key: str) -> None:
        record = self._failures.get(key)
        if not record:
            return
        first_ts, count, locked_until = record[0], record[1], record[2]
        now = time.time()
        if locked_until > now:
            remaining = int(locked_until - now)
            raise AuthError(
                "TOO_MANY_ATTEMPTS",
                f"登录失败过多，请在约 {remaining // 60 + 1} 分钟后重试",
                http_status=429,
            )
        # 窗口过期则清零
        if now - first_ts > _THROTTLE_WINDOW:
            self._failures.pop(key, None)

    def _record_failure(self, key: str) -> None:
        now = time.time()
        record = self._failures.get(key)
        if not record or now - record[0] > _THROTTLE_WINDOW:
            self._failures[key] = [now, 1.0, 0.0]
            return
        record[1] += 1.0
        if record[1] >= _THROTTLE_MAX_FAILURES:
            record[2] = now + _THROTTLE_LOCK

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        for item in (payload.get("users") if isinstance(payload, dict) else []) or []:
            try:
                user = _User.from_dict(item)
            except (KeyError, ValueError, TypeError):
                continue
            self._users[user.username] = user

    def _save(self) -> None:
        """原子写：先写 .tmp 再 replace（调用方已在锁内）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {"version": 1, "users": [user.to_dict() for user in self._users.values()]}
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp_path.replace(self.path)
