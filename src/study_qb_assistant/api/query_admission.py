"""查题请求的并发与速率准入控制。

该模块只保存进程内的短期计数，不保存原始 API Key、题干或请求内容。
生产部署当前为单进程实例；未来扩展多副本时，应将同一契约替换为共享限流存储。
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from math import ceil
from threading import RLock
import time
from typing import Mapping


DEFAULT_QUERY_PROTECTION = {
    "query_rate_limit_enabled": True,
    "query_rate_limit_window_seconds": 60,
    "query_rate_limit_requests_per_user": 60,
    "query_max_active_requests_per_user": 2,
    "query_max_active_requests": 8,
}

HARD_MAX_ACTIVE_REQUESTS = 32
HARD_MAX_ACTIVE_REQUESTS_PER_USER = 8
HARD_MAX_RATE_WINDOW_SECONDS = 3600
HARD_MAX_RATE_REQUESTS_PER_USER = 600
MAX_PRINCIPALS = 10_000
PRINCIPAL_IDLE_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class QueryAdmissionDecision:
    """描述一次请求为何被准入或拒绝。"""

    allowed: bool
    reason: str = ""
    retry_after_seconds: int = 1


@dataclass(slots=True)
class _PrincipalState:
    active: int = 0
    accepted_at: deque[float] | None = None
    last_seen: float = 0.0


class QueryAdmissionLease:
    """一次已准入查题请求的可幂等释放凭证。"""

    def __init__(self, controller: "QueryAdmissionController", principal: str) -> None:
        self._controller = controller
        self._principal = principal
        self._released = False

    def release(self) -> None:
        """释放活动请求占用；重复调用不会重复扣减计数。"""

        if self._released:
            return
        self._released = True
        self._controller.release(self._principal)

    def __enter__(self) -> "QueryAdmissionLease":
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.release()


class QueryAdmissionController:
    """单进程查题准入控制器。

    活动请求使用全局与主体两层计数，窗口请求使用主体时间队列。所有状态变更
    由同一把锁保护，避免 FastAPI 同步线程池并发时超发额度或泄漏活动槽位。
    """

    def __init__(
        self,
        *,
        max_principals: int = MAX_PRINCIPALS,
        principal_idle_seconds: float = PRINCIPAL_IDLE_SECONDS,
    ) -> None:
        self._lock = RLock()
        self._states: OrderedDict[str, _PrincipalState] = OrderedDict()
        self._active_requests = 0
        self._max_principals = max(100, max_principals)
        self._principal_idle_seconds = max(60.0, principal_idle_seconds)
        self._next_idle_sweep = 0.0
        self._rejected_total = 0
        self._rejected_by_reason: dict[str, int] = {
            "global_concurrency": 0,
            "user_concurrency": 0,
            "rate_limit": 0,
        }

    def try_acquire(
        self,
        principal: str,
        policy: Mapping[str, object] | None = None,
    ) -> tuple[QueryAdmissionLease | None, QueryAdmissionDecision]:
        """按当前配置尝试准入一个查题请求，不等待、不创建无界队列。"""

        normalized = normalize_query_protection(policy)
        key = principal.strip() or "anonymous"
        now = time.monotonic()
        with self._lock:
            self._evict_idle(now)
            state = self._states.get(key)
            if state is not None:
                self._touch(key, state, now)

            if self._active_requests >= normalized["max_active_requests"]:
                return self._reject("global_concurrency", retry_after_seconds=1)

            if state is None:
                if len(self._states) >= self._max_principals:
                    self._evict_oldest_idle()
                state = _PrincipalState(last_seen=now, accepted_at=deque())
                self._states[key] = state
            assert state.accepted_at is not None
            self._prune_window(state.accepted_at, now, normalized["window_seconds"])
            if state.active >= normalized["max_active_requests_per_user"]:
                return self._reject("user_concurrency", retry_after_seconds=1)
            if (
                normalized["rate_limit_enabled"]
                and len(state.accepted_at) >= normalized["requests_per_user"]
            ):
                oldest = state.accepted_at[0] if state.accepted_at else now
                retry_after = max(
                    1,
                    ceil(normalized["window_seconds"] - (now - oldest)),
                )
                return self._reject("rate_limit", retry_after_seconds=retry_after)

            self._active_requests += 1
            state.active += 1
            if normalized["rate_limit_enabled"]:
                state.accepted_at.append(now)
            return QueryAdmissionLease(self, key), QueryAdmissionDecision(allowed=True)

    def release(self, principal: str) -> None:
        """释放主体活动请求计数。"""

        key = principal.strip() or "anonymous"
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return
            self._active_requests = max(0, self._active_requests - 1)
            self._touch(key, state, time.monotonic())
            state.active = max(0, state.active - 1)

    def status(self, policy: Mapping[str, object] | None = None) -> dict[str, object]:
        """返回非敏感运行统计和当前生效配置。"""

        normalized = normalize_query_protection(policy)
        with self._lock:
            active_per_user = max(
                (state.active for state in self._states.values()),
                default=0,
            )
            return {
                "active_requests": self._active_requests,
                "active_requests_per_user": active_per_user,
                "active_principals": sum(1 for state in self._states.values() if state.active),
                "rejected_total": self._rejected_total,
                "rejected_by_global_limit": self._rejected_by_reason["global_concurrency"],
                "rejected_by_user_limit": self._rejected_by_reason["user_concurrency"],
                "rejected_by_rate_limit": self._rejected_by_reason["rate_limit"],
                "configured_rate_limit_enabled": normalized["rate_limit_enabled"],
                "configured_window_seconds": normalized["window_seconds"],
                "configured_requests_per_user": normalized["requests_per_user"],
                "configured_global_limit": normalized["max_active_requests"],
                "configured_user_concurrency": normalized["max_active_requests_per_user"],
            }

    def _reject(self, reason: str, *, retry_after_seconds: int) -> tuple[None, QueryAdmissionDecision]:
        self._rejected_total += 1
        self._rejected_by_reason[reason] += 1
        return None, QueryAdmissionDecision(
            allowed=False,
            reason=reason,
            retry_after_seconds=max(1, retry_after_seconds),
        )

    def _evict_idle(self, now: float) -> None:
        if now < self._next_idle_sweep:
            return
        self._next_idle_sweep = now + min(60.0, self._principal_idle_seconds / 4)
        cutoff = now - self._principal_idle_seconds
        while self._states:
            key, state = next(iter(self._states.items()))
            if state.active or state.last_seen >= cutoff:
                break
            self._states.pop(key, None)

    def _evict_oldest_idle(self) -> None:
        oldest_idle = next(
            ((key, state) for key, state in self._states.items() if state.active == 0),
            None,
        )
        if oldest_idle is not None:
            self._states.pop(oldest_idle[0], None)

    def _touch(self, key: str, state: _PrincipalState, now: float) -> None:
        state.last_seen = now
        self._states.move_to_end(key)

    @staticmethod
    def _prune_window(values: deque[float], now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        while values and values[0] <= cutoff:
            values.popleft()


def normalize_query_protection(policy: Mapping[str, object] | None) -> dict[str, int | bool]:
    """解析并钳制动态配置；异常值回退到安全默认值。"""

    source = policy or {}
    return {
        "rate_limit_enabled": _bool_value(
            source.get("query_rate_limit_enabled"),
            default=True,
        ),
        "window_seconds": _bounded_int(
            source.get("query_rate_limit_window_seconds"),
            default=60,
            minimum=10,
            maximum=HARD_MAX_RATE_WINDOW_SECONDS,
        ),
        "requests_per_user": _bounded_int(
            source.get("query_rate_limit_requests_per_user"),
            default=60,
            minimum=1,
            maximum=HARD_MAX_RATE_REQUESTS_PER_USER,
        ),
        "max_active_requests_per_user": _bounded_int(
            source.get("query_max_active_requests_per_user"),
            default=2,
            minimum=1,
            maximum=HARD_MAX_ACTIVE_REQUESTS_PER_USER,
        ),
        "max_active_requests": _bounded_int(
            source.get("query_max_active_requests"),
            default=8,
            minimum=1,
            maximum=HARD_MAX_ACTIVE_REQUESTS,
        ),
    }


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}
