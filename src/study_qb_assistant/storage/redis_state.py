"""Redis 状态存储辅助。"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..auth.records import SessionRecord

try:
    import redis
except Exception:  # pragma: no cover - 依赖缺失时走回退分支
    redis = None  # type: ignore[assignment]


def build_redis_client_from_env():
    """按环境变量构建 Redis 客户端，未配置则返回 None。"""
    if redis is None:
        return None
    raw_url = os.getenv("STQB_REDIS_URL", "").strip()
    if not raw_url:
        return None
    return redis.Redis.from_url(raw_url, decode_responses=True)


def build_session_store_from_env():
    """按环境变量构建会话存储，默认回退为内存实现。"""
    client = build_redis_client_from_env()
    if client is None:
        return InMemorySessionStore()
    try:
        client.ping()
    except Exception:
        return InMemorySessionStore()
    return RedisSessionStore(client)


def build_recent_event_store_from_env(maxlen: int = 80):
    """按环境变量构建最近事件存储，默认回退为内存实现。"""
    client = build_redis_client_from_env()
    if client is None:
        return InMemoryRecentEventStore(maxlen=maxlen)
    try:
        client.ping()
    except Exception:
        return InMemoryRecentEventStore(maxlen=maxlen)
    return RedisRecentEventStore(client, maxlen=maxlen)


class InMemorySessionStore:
    """默认的内存会话存储。"""

    def __init__(self) -> None:
        self._sessions: dict[str, "SessionRecord"] = {}
        self._user_tokens: dict[str, set[str]] = {}

    def save(self, token: str, session: "SessionRecord", ttl_seconds: int) -> None:
        self._sessions[token] = session
        self._user_tokens.setdefault(session.username, set()).add(token)

    def read(self, token: str) -> "SessionRecord | None":
        return self._sessions.get(token)

    def delete(self, token: str) -> None:
        session = self._sessions.pop(token, None)
        if session is None:
            return
        tokens = self._user_tokens.get(session.username)
        if not tokens:
            return
        tokens.discard(token)
        if not tokens:
            self._user_tokens.pop(session.username, None)

    def delete_user_sessions(self, username: str) -> None:
        for token in list(self._user_tokens.get(username) or ()):
            self._sessions.pop(token, None)
        self._user_tokens.pop(username, None)


class RedisSessionStore:
    """基于 Redis 的会话存储。"""

    def __init__(self, client) -> None:
        self.client = client

    def save(self, token: str, session: "SessionRecord", ttl_seconds: int) -> None:
        payload = json.dumps(
            {
                "username": session.username,
                "role": session.role,
                "expires_at": session.expires_at,
            },
            ensure_ascii=False,
        )
        session_key = f"stqb:session:{token}"
        user_key = f"stqb:user-sessions:{session.username}"
        pipe = self.client.pipeline()
        pipe.setex(session_key, ttl_seconds, payload)
        pipe.sadd(user_key, token)
        pipe.expire(user_key, ttl_seconds)
        pipe.execute()

    def read(self, token: str) -> "SessionRecord | None":
        from ..auth.records import SessionRecord

        session_key = f"stqb:session:{token}"
        payload = self.client.get(session_key)
        if not payload:
            return None
        data = json.loads(payload)
        return SessionRecord(
            username=str(data["username"]),
            role=str(data["role"]),
            expires_at=float(data["expires_at"]),
        )

    def delete(self, token: str) -> None:
        session = self.read(token)
        session_key = f"stqb:session:{token}"
        pipe = self.client.pipeline()
        pipe.delete(session_key)
        if session is not None:
            pipe.srem(f"stqb:user-sessions:{session.username}", token)
        pipe.execute()

    def delete_user_sessions(self, username: str) -> None:
        user_key = f"stqb:user-sessions:{username}"
        tokens = self.client.smembers(user_key) or ()
        pipe = self.client.pipeline()
        for token in tokens:
            pipe.delete(f"stqb:session:{token}")
        pipe.delete(user_key)
        pipe.execute()


class InMemoryRecentEventStore:
    """默认的最近事件内存存储。"""

    def __init__(self, maxlen: int = 80) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def append(self, entry: dict[str, Any]) -> None:
        self._events.append(entry)

    def recent(self, limit: int) -> list[dict[str, Any]]:
        return list(self._events)[-limit:]


class RedisRecentEventStore:
    """基于 Redis 列表的最近事件存储。"""

    def __init__(self, client, *, maxlen: int = 80) -> None:
        self.client = client
        self.maxlen = maxlen
        self.key = "stqb:recent-events"

    def append(self, entry: dict[str, Any]) -> None:
        pipe = self.client.pipeline()
        pipe.rpush(self.key, json.dumps(entry, ensure_ascii=False))
        pipe.ltrim(self.key, -self.maxlen, -1)
        pipe.execute()

    def recent(self, limit: int) -> list[dict[str, Any]]:
        items = self.client.lrange(self.key, -limit, -1)
        return [json.loads(item) for item in items]
