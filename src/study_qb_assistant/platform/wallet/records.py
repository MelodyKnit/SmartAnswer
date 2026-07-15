"""钱包与兑换码记录。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class RedeemCodeRecord:
    """兑换码记录。"""

    code_id: str
    code: str
    kind: str
    points: int
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
            source=str(payload.get("source") or ""),
            source_id=(str(payload["source_id"]) if payload.get("source_id") else None),
            status=str(payload.get("status") or "completed"),
            created_by=str(payload.get("created_by") or ""),
            created_at=float(payload.get("created_at") or time.time()),
        )
