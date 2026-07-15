"""系统公告记录。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class AnnouncementRecord:
    """系统公告记录。"""

    announcement_id: str
    title: str
    content: str
    level: str
    audience: str
    status: str
    pinned: bool
    starts_at: float
    ends_at: float
    created_by: str
    created_at: float
    updated_at: float
    published_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "announcement_id": self.announcement_id,
            "title": self.title,
            "content": self.content,
            "level": self.level,
            "audience": self.audience,
            "status": self.status,
            "pinned": self.pinned,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "AnnouncementRecord":
        return cls(
            announcement_id=str(payload["announcement_id"]),
            title=str(payload.get("title") or ""),
            content=str(payload.get("content") or ""),
            level=str(payload.get("level") or "info"),
            audience=str(payload.get("audience") or "all"),
            status=str(payload.get("status") or "draft"),
            pinned=bool(payload.get("pinned") or False),
            starts_at=float(payload.get("starts_at") or 0.0),
            ends_at=float(payload.get("ends_at") or 0.0),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            published_at=float(payload.get("published_at") or 0.0),
        )
