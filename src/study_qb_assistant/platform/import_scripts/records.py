"""导入脚本记录。"""

from __future__ import annotations

import time
from dataclasses import dataclass


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
    description: str = ""
    requires_token: bool = True
    tags: tuple[str, ...] = ()
    builtin: bool = False
    is_default: bool = False
    ocs_config: tuple[dict, ...] = ()

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
            "description": self.description,
            "requires_token": self.requires_token,
            "tags": list(self.tags),
            "builtin": self.builtin,
            "is_default": self.is_default,
            "ocs_config": list(self.ocs_config),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ImportScriptRecord":
        return cls(
            script_id=str(payload["script_id"]),
            name=str(payload.get("name") or ""),
            integration_id=(
                str(payload["integration_id"]) if payload.get("integration_id") else None
            ),
            token_id=(str(payload["token_id"]) if payload.get("token_id") else None),
            target=str(payload.get("target") or "ocs"),
            content=str(payload.get("content") or ""),
            status=str(payload.get("status") or "active"),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            description=str(payload.get("description") or ""),
            requires_token=bool(payload.get("requires_token", True)),
            tags=tuple(str(item) for item in payload.get("tags") or ()),
            builtin=bool(payload.get("builtin", False)),
            is_default=bool(payload.get("is_default", False)),
            ocs_config=tuple(dict(item) for item in payload.get("ocs_config") or ()),
        )
