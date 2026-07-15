"""通知与阅读回执记录。"""

from __future__ import annotations

import time
from dataclasses import dataclass


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
class NotificationReadReceiptRecord:
    """通知中心按用户维度记录的已读回执。"""

    user_id: str
    source: str
    item_id: str
    item_updated_at: float
    read_at: float

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "source": self.source,
            "item_id": self.item_id,
            "item_updated_at": self.item_updated_at,
            "read_at": self.read_at,
        }
