"""公告接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class AnnouncementCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    content: str = ""
    level: str = "info"
    audience: str = "all"
    status: str = "draft"
    pinned: bool = False
    starts_at: float = 0.0
    ends_at: float = 0.0


class AnnouncementUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    content: str | None = None
    level: str | None = None
    audience: str | None = None
    status: str | None = None
    pinned: bool | None = None
    starts_at: float | None = None
    ends_at: float | None = None
