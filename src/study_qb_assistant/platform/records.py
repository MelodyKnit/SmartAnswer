"""平台领域持久化记录模型。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class ApiTokenRecord:
    """用户 API 令牌的持久化记录。"""

    token_id: str
    user_id: str
    key_hash: str
    key_mask: str
    description: str
    status: str
    created_at: float
    last_used_at: float = 0.0
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "key_hash": self.key_hash,
            "key_mask": self.key_mask,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ApiTokenRecord":
        return cls(
            token_id=str(payload["token_id"]),
            user_id=str(payload["user_id"]),
            key_hash=str(payload["key_hash"]),
            key_mask=str(payload["key_mask"]),
            description=str(payload.get("description") or ""),
            status=str(payload.get("status") or "active"),
            created_at=float(payload.get("created_at") or time.time()),
            last_used_at=float(payload.get("last_used_at") or 0.0),
            usage_count=int(payload.get("usage_count") or 0),
        )


@dataclass(slots=True)
class UsageLogRecord:
    """单次查题使用记录。"""

    log_id: str
    user_id: str
    username: str
    token_id: str | None
    title: str
    question_type: str
    resolution_mode: str
    answer: str | None
    confidence: float
    points_cost: int
    provider: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "user_id": self.user_id,
            "username": self.username,
            "token_id": self.token_id,
            "title": self.title,
            "question_type": self.question_type,
            "resolution_mode": self.resolution_mode,
            "answer": self.answer,
            "confidence": self.confidence,
            "points_cost": self.points_cost,
            "provider": self.provider,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "UsageLogRecord":
        return cls(
            log_id=str(payload["log_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            title=str(payload.get("title") or ""),
            question_type=str(payload.get("question_type") or "unknown"),
            resolution_mode=str(payload.get("resolution_mode") or ""),
            answer=(str(payload["answer"]) if payload.get("answer") is not None else None),
            confidence=float(payload.get("confidence") or 0.0),
            points_cost=int(payload.get("points_cost") or 0),
            provider=str(payload.get("provider") or ""),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class FeedbackRecord:
    """用户错题反馈记录。"""

    feedback_id: str
    user_id: str
    username: str
    usage_log_id: str | None
    title: str
    content: str
    image_urls: tuple[str, ...]
    status: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "user_id": self.user_id,
            "username": self.username,
            "usage_log_id": self.usage_log_id,
            "title": self.title,
            "content": self.content,
            "image_urls": list(self.image_urls),
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "FeedbackRecord":
        return cls(
            feedback_id=str(payload["feedback_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            usage_log_id=(str(payload["usage_log_id"]) if payload.get("usage_log_id") else None),
            title=str(payload.get("title") or ""),
            content=str(payload.get("content") or ""),
            image_urls=tuple(str(url) for url in payload.get("image_urls") or ()),
            status=str(payload.get("status") or "open"),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class WalletProfileRecord:
    """用户钱包档案。"""

    user_id: str
    subscription_expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "subscription_expires_at": self.subscription_expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "WalletProfileRecord":
        return cls(
            user_id=str(payload["user_id"]),
            subscription_expires_at=float(payload.get("subscription_expires_at") or 0.0),
        )


@dataclass(slots=True)
class RedeemCodeRecord:
    """兑换码记录。"""

    code_id: str
    code: str
    kind: str
    points: int
    subscription_days: int
    max_uses: int
    used_uses: int
    status: str
    created_by: str
    created_at: float
    expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "code_id": self.code_id,
            "code": self.code,
            "kind": self.kind,
            "points": self.points,
            "subscription_days": self.subscription_days,
            "max_uses": self.max_uses,
            "used_uses": self.used_uses,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "RedeemCodeRecord":
        return cls(
            code_id=str(payload["code_id"]),
            code=str(payload["code"]),
            kind=str(payload.get("kind") or "points"),
            points=int(payload.get("points") or 0),
            subscription_days=int(payload.get("subscription_days") or 0),
            max_uses=int(payload.get("max_uses") or 1),
            used_uses=int(payload.get("used_uses") or 0),
            status=str(payload.get("status") or "active"),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
            expires_at=float(payload.get("expires_at") or 0.0),
        )


@dataclass(slots=True)
class WalletOrderRecord:
    """钱包订单与权益变更流水。"""

    order_id: str
    user_id: str
    username: str
    kind: str
    points_delta: int
    subscription_days: int
    source: str
    source_id: str | None
    status: str
    created_by: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "username": self.username,
            "kind": self.kind,
            "points_delta": self.points_delta,
            "subscription_days": self.subscription_days,
            "source": self.source,
            "source_id": self.source_id,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "WalletOrderRecord":
        return cls(
            order_id=str(payload["order_id"]),
            user_id=str(payload["user_id"]),
            username=str(payload["username"]),
            kind=str(payload.get("kind") or "points"),
            points_delta=int(payload.get("points_delta") or 0),
            subscription_days=int(payload.get("subscription_days") or 0),
            source=str(payload.get("source") or ""),
            source_id=(str(payload["source_id"]) if payload.get("source_id") else None),
            status=str(payload.get("status") or "completed"),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class NotificationRecord:
    """消息中心通知记录。"""

    notification_id: str
    user_id: str | None
    level: str
    category: str
    title: str
    content: str
    read: bool
    created_at: float

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "read": self.read,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "NotificationRecord":
        return cls(
            notification_id=str(payload["notification_id"]),
            user_id=(str(payload["user_id"]) if payload.get("user_id") else None),
            level=str(payload.get("level") or "info"),
            category=str(payload.get("category") or "system"),
            title=str(payload.get("title") or ""),
            content=str(payload.get("content") or ""),
            read=bool(payload.get("read") or False),
            created_at=float(payload.get("created_at") or time.time()),
        )


@dataclass(slots=True)
class IntegrationRecord:
    """第三方接入点记录。"""

    integration_id: str
    name: str
    platform: str
    base_url: str
    token_id: str | None
    status: str
    description: str
    created_at: float
    updated_at: float
    last_test_at: float = 0.0
    last_test_status: str = "unknown"
    last_error: str = ""

    def to_dict(self) -> dict:
        return {
            "integration_id": self.integration_id,
            "name": self.name,
            "platform": self.platform,
            "base_url": self.base_url,
            "token_id": self.token_id,
            "status": self.status,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_test_at": self.last_test_at,
            "last_test_status": self.last_test_status,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "IntegrationRecord":
        return cls(
            integration_id=str(payload["integration_id"]),
            name=str(payload.get("name") or ""),
            platform=str(payload.get("platform") or "generic"),
            base_url=str(payload.get("base_url") or ""),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            status=str(payload.get("status") or "active"),
            description=str(payload.get("description") or ""),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            last_test_at=float(payload.get("last_test_at") or 0.0),
            last_test_status=str(payload.get("last_test_status") or "unknown"),
            last_error=str(payload.get("last_error") or ""),
        )


@dataclass(slots=True)
class ImportScriptRecord:
    """导入脚本记录。"""

    script_id: str
    name: str
    integration_id: str | None
    token_id: str | None
    target: str
    content: str
    status: str
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "script_id": self.script_id,
            "name": self.name,
            "integration_id": self.integration_id,
            "token_id": self.token_id,
            "target": self.target,
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ImportScriptRecord":
        return cls(
            script_id=str(payload["script_id"]),
            name=str(payload.get("name") or ""),
            integration_id=(str(payload["integration_id"]) if payload.get("integration_id") else None),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            target=str(payload.get("target") or "ocs"),
            content=str(payload.get("content") or ""),
            status=str(payload.get("status") or "active"),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
        )


@dataclass(slots=True)
class QuotaPackageRecord:
    """额度套餐记录。"""

    package_id: str
    name: str
    kind: str
    points: int
    subscription_days: int
    price: float
    status: str
    description: str
    sort_order: int
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "package_id": self.package_id,
            "name": self.name,
            "kind": self.kind,
            "points": self.points,
            "subscription_days": self.subscription_days,
            "price": self.price,
            "status": self.status,
            "description": self.description,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "QuotaPackageRecord":
        return cls(
            package_id=str(payload["package_id"]),
            name=str(payload.get("name") or ""),
            kind=str(payload.get("kind") or "points"),
            points=int(payload.get("points") or 0),
            subscription_days=int(payload.get("subscription_days") or 0),
            price=float(payload.get("price") or 0.0),
            status=str(payload.get("status") or "active"),
            description=str(payload.get("description") or ""),
            sort_order=int(payload.get("sort_order") or 0),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
        )


@dataclass(slots=True)
class RolePermissionRecord:
    """角色权限矩阵记录。"""

    role_id: str
    permissions: tuple[str, ...]
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "role_id": self.role_id,
            "permissions": list(self.permissions),
            "updated_at": self.updated_at,
        }
