"""系统公告管理服务。"""

from __future__ import annotations

import secrets
import time

from ...auth import AuthError
from ..base import PlatformDomainService
from .records import AnnouncementRecord

ANNOUNCEMENT_LEVELS = {"info", "success", "warning", "danger"}
ANNOUNCEMENT_STATUSES = {"draft", "published", "archived"}


class AnnouncementService(PlatformDomainService):
    """AnnouncementService 领域实现。"""

    def create_announcement(
        self,
        *,
        title: str,
        content: str,
        level: str = "info",
        audience: str = "all",
        status: str = "draft",
        pinned: bool = False,
        starts_at: float = 0.0,
        ends_at: float = 0.0,
        created_by: str = "",
        valid_role_ids: set[str],
    ) -> dict:
        """创建系统公告。"""

        now = time.time()
        normalized = self._normalize_announcement_payload(
            title=title,
            content=content,
            level=level,
            audience=audience,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
            valid_role_ids=valid_role_ids,
        )
        record = AnnouncementRecord(
            announcement_id=secrets.token_hex(12),
            title=normalized["title"],
            content=normalized["content"],
            level=normalized["level"],
            audience=normalized["audience"],
            status=normalized["status"],
            pinned=bool(pinned),
            starts_at=normalized["starts_at"],
            ends_at=normalized["ends_at"],
            created_by=created_by,
            created_at=now,
            updated_at=now,
            published_at=now if normalized["status"] == "published" else 0.0,
        )
        with self.lock:
            return self.repository.save_announcement(record).to_dict()

    def update_announcement(
        self,
        announcement_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        level: str | None = None,
        audience: str | None = None,
        status: str | None = None,
        pinned: bool | None = None,
        starts_at: float | None = None,
        ends_at: float | None = None,
        valid_role_ids: set[str],
    ) -> dict:
        """更新系统公告。"""

        with self.lock:
            record = self.repository.get_announcement(announcement_id)
            if record is None:
                raise AuthError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", http_status=404)
            normalized = self._normalize_announcement_payload(
                title=record.title if title is None else title,
                content=record.content if content is None else content,
                level=record.level if level is None else level,
                audience=record.audience if audience is None else audience,
                status=record.status if status is None else status,
                starts_at=record.starts_at if starts_at is None else starts_at,
                ends_at=record.ends_at if ends_at is None else ends_at,
                # 已删除角色可能仍被历史公告引用；允许继续编辑并改投其他角色。
                valid_role_ids={*valid_role_ids, record.audience},
            )
            published_at = record.published_at
            if normalized["status"] == "published" and published_at <= 0:
                published_at = time.time()
            updated = AnnouncementRecord(
                announcement_id=record.announcement_id,
                title=normalized["title"],
                content=normalized["content"],
                level=normalized["level"],
                audience=normalized["audience"],
                status=normalized["status"],
                pinned=record.pinned if pinned is None else bool(pinned),
                starts_at=normalized["starts_at"],
                ends_at=normalized["ends_at"],
                created_by=record.created_by,
                created_at=record.created_at,
                updated_at=time.time(),
                published_at=published_at,
            )
            return self.repository.save_announcement(updated).to_dict()

    def archive_announcement(
        self, announcement_id: str, *, valid_role_ids: set[str]
    ) -> dict:
        """归档公告，不物理删除。"""

        return self.update_announcement(
            announcement_id,
            status="archived",
            valid_role_ids=valid_role_ids,
        )

    def list_announcements(
        self,
        *,
        keyword: str = "",
        status: str = "",
        level: str = "",
        audience: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        """读取公告管理列表。"""

        normalized_limit = max(1, min(int(limit or 20), 100))
        normalized_page = max(1, int(page or 1))
        offset = (normalized_page - 1) * normalized_limit
        with self.lock:
            items = self.repository.list_announcements(
                keyword=keyword,
                status=status,
                level=level,
                audience=audience,
                limit=normalized_limit,
                offset=offset,
            )
            total = self.repository.count_announcements(
                keyword=keyword,
                status=status,
                level=level,
                audience=audience,
            )
        return {
            "announcements": [item.to_dict() for item in items],
            "total": total,
            "page": normalized_page,
            "limit": normalized_limit,
        }

    def list_active_announcements(self, *, role: str, limit: int = 10) -> list[dict]:
        """读取当前角色可见的有效公告。"""

        with self.lock:
            records = self.repository.list_active_announcements(
                role=role,
                now=time.time(),
                limit=limit,
            )
        return [record.to_dict() for record in records]

    @staticmethod
    def _normalize_announcement_payload(
        *,
        title: str,
        content: str,
        level: str,
        audience: str,
        status: str,
        starts_at: float,
        ends_at: float,
        valid_role_ids: set[str],
    ) -> dict:
        """校验并规范化公告输入。"""

        normalized_title = (title or "").strip()
        normalized_content = (content or "").strip()
        if not normalized_title:
            raise AuthError("INVALID_INPUT", "请填写公告标题", http_status=400)
        if len(normalized_title) > 120:
            raise AuthError("INVALID_INPUT", "公告标题不能超过 120 个字符", http_status=400)
        if not normalized_content:
            raise AuthError("INVALID_INPUT", "请填写公告内容", http_status=400)
        if len(normalized_content) > 3000:
            raise AuthError("INVALID_INPUT", "公告内容不能超过 3000 个字符", http_status=400)

        normalized_level = (level or "info").strip()
        normalized_audience = (audience or "all").strip()
        normalized_status = (status or "draft").strip()
        if normalized_level not in ANNOUNCEMENT_LEVELS:
            raise AuthError("INVALID_INPUT", "公告等级不支持", http_status=400)
        if normalized_audience not in {"all", *valid_role_ids}:
            raise AuthError("INVALID_INPUT", "公告投放范围不支持", http_status=400)
        if normalized_status not in ANNOUNCEMENT_STATUSES:
            raise AuthError("INVALID_INPUT", "公告状态不支持", http_status=400)

        normalized_starts_at = max(0.0, float(starts_at or 0.0))
        normalized_ends_at = max(0.0, float(ends_at or 0.0))
        if normalized_starts_at > 0 and normalized_ends_at > 0:
            if normalized_ends_at <= normalized_starts_at:
                raise AuthError("INVALID_INPUT", "结束时间必须晚于开始时间", http_status=400)
        return {
            "title": normalized_title,
            "content": normalized_content,
            "level": normalized_level,
            "audience": normalized_audience,
            "status": normalized_status,
            "starts_at": normalized_starts_at,
            "ends_at": normalized_ends_at,
        }
