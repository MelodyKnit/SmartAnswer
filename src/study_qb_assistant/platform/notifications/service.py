"""用户通知与通知中心服务。"""

from __future__ import annotations

import secrets
import time
from threading import RLock
from typing import Any

from ...auth import AuthError
from ..base import PlatformDomainService
from ..announcements.records import AnnouncementRecord
from .records import NotificationReadReceiptRecord, NotificationRecord


class NotificationService(PlatformDomainService):
    """NotificationService 领域实现。"""

    def __init__(self, repository: Any, announcement_repository: Any, lock: RLock) -> None:
        super().__init__(repository, lock)
        self.announcement_repository = announcement_repository

    def create_notification(
        self,
        *,
        user_id: str | None,
        level: str,
        category: str,
        title: str,
        content: str,
    ) -> dict:
        """创建一条消息中心通知。"""
        record = NotificationRecord(
            notification_id=secrets.token_hex(12),
            user_id=user_id,
            level=level or "info",
            category=category or "system",
            title=title,
            content=content,
            read=False,
            created_at=time.time(),
        )
        with self.lock:
            self.repository.save_notification(record)
        return record.to_dict()

    def list_notifications(
        self, *, user_id: str | None = None, status: str = "", limit: int = 20
    ) -> list[dict]:
        """列出消息中心通知。"""
        with self.lock:
            return [
                item.to_dict()
                for item in self.repository.list_notifications(
                    user_id=user_id, status=status, limit=limit
                )
            ]

    def mark_notification_read(
        self,
        notification_id: str,
        *,
        user_id: str | None = None,
        read: bool = True,
    ) -> dict:
        """标记单条消息的已读状态。"""
        with self.lock:
            record = self.repository.get_notification(notification_id)
            if record is None:
                raise AuthError("NOTIFICATION_NOT_FOUND", "消息不存在", http_status=404)
            if record.user_id not in {None, user_id}:
                raise AuthError("NOTIFICATION_FORBIDDEN", "无权操作该消息", http_status=403)
            record.read = bool(read)
            self.repository.save_notification(record)
            return record.to_dict()

    def mark_all_notifications_read(self, *, user_id: str | None = None) -> int:
        """批量标记消息为已读。"""
        count = 0
        with self.lock:
            for record in self.repository.list_notifications(
                user_id=user_id, status="unread", limit=500
            ):
                record.read = True
                self.repository.save_notification(record)
                count += 1
        return count

    def notification_center(
        self,
        *,
        user_id: str,
        role: str,
        status: str = "",
        source: str = "",
        limit: int = 20,
    ) -> dict:
        """聚合当前用户可见的公告和消息通知。"""

        normalized_limit = max(1, min(int(limit or 20), 100))
        normalized_source = (source or "").strip()
        if normalized_source not in {"", "announcement", "notification"}:
            raise AuthError("INVALID_SOURCE", "通知来源无效", http_status=400)
        normalized_status = (status or "").strip()
        if normalized_status not in {"", "read", "unread"}:
            raise AuthError("INVALID_STATUS", "通知状态无效", http_status=400)

        with self.lock:
            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source=normalized_source,
                limit=500,
            )

        unread_count = sum(1 for item in items if not item["read"])
        if normalized_status == "read":
            items = [item for item in items if item["read"]]
        elif normalized_status == "unread":
            items = [item for item in items if not item["read"]]
        return {
            "items": items[:normalized_limit],
            "unread_count": unread_count,
            "total": len(items),
        }

    def mark_notification_center_item_read(
        self,
        *,
        user_id: str,
        role: str,
        source: str,
        item_id: str,
    ) -> dict:
        """按通知中心来源标记单条公告或消息为已读。"""

        normalized_source = (source or "").strip()
        with self.lock:
            if normalized_source == "announcement":
                announcement_record = self.announcement_repository.get_announcement(item_id)
                now = time.time()
                if announcement_record is None or not self.announcement_visible_for_role(
                    announcement_record, role=role, now=now
                ):
                    raise AuthError("ANNOUNCEMENT_NOT_FOUND", "公告不存在", http_status=404)
                self.repository.save_notification_read_receipt(
                    NotificationReadReceiptRecord(
                        user_id=user_id,
                        source="announcement",
                        item_id=announcement_record.announcement_id,
                        item_updated_at=announcement_record.updated_at,
                        read_at=now,
                    )
                )
            elif normalized_source == "notification":
                notification_record = self.repository.get_notification(item_id)
                if notification_record is None:
                    raise AuthError("NOTIFICATION_NOT_FOUND", "消息不存在", http_status=404)
                if notification_record.user_id not in {None, user_id}:
                    raise AuthError("NOTIFICATION_FORBIDDEN", "无权操作该消息", http_status=403)
                if notification_record.user_id is None:
                    self.repository.save_notification_read_receipt(
                        NotificationReadReceiptRecord(
                            user_id=user_id,
                            source="notification",
                            item_id=notification_record.notification_id,
                            item_updated_at=notification_record.created_at,
                            read_at=time.time(),
                        )
                    )
                else:
                    notification_record.read = True
                    self.repository.save_notification(notification_record)
            else:
                raise AuthError("INVALID_SOURCE", "通知来源无效", http_status=400)

            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source=normalized_source,
                limit=100,
            )
        for item in items:
            if item["source"] == normalized_source and item["item_id"] == item_id:
                return item
        raise AuthError("NOTIFICATION_CENTER_ITEM_NOT_FOUND", "通知不存在", http_status=404)

    def mark_all_notification_center_read(self, *, user_id: str, role: str) -> int:
        """批量标记通知中心的可见未读内容。"""

        with self.lock:
            items = self.build_notification_center_items(
                user_id=user_id,
                role=role,
                source="",
                limit=500,
            )
            unread_items = [item for item in items if not item["read"]]
            for item in unread_items:
                if item["source"] == "announcement":
                    self.repository.save_notification_read_receipt(
                        NotificationReadReceiptRecord(
                            user_id=user_id,
                            source="announcement",
                            item_id=item["item_id"],
                            item_updated_at=float(item["updated_at"] or 0.0),
                            read_at=time.time(),
                        )
                    )
                else:
                    record = self.repository.get_notification(str(item["item_id"]))
                    if record is None:
                        continue
                    if record.user_id is None:
                        self.repository.save_notification_read_receipt(
                            NotificationReadReceiptRecord(
                                user_id=user_id,
                                source="notification",
                                item_id=record.notification_id,
                                item_updated_at=record.created_at,
                                read_at=time.time(),
                            )
                        )
                    else:
                        record.read = True
                        self.repository.save_notification(record)
        return len(unread_items)

    def build_notification_center_items(
        self, *, user_id: str, role: str, source: str, limit: int
    ) -> list[dict]:
        """构建通知中心统一列表，保持公告和通知各自的存储语义。"""

        items: list[dict] = []
        keys: list[tuple[str, str]] = []
        notification_records: list[NotificationRecord] = []
        announcement_records: list[AnnouncementRecord] = []
        if source in {"", "notification"}:
            notification_records = self.repository.list_notifications(
                user_id=user_id, limit=max(1, min(limit, 500))
            )
            keys.extend(("notification", item.notification_id) for item in notification_records)
        if source in {"", "announcement"}:
            announcement_records = self.announcement_repository.list_active_announcements(
                role=role, now=time.time(), limit=max(1, min(limit, 500))
            )
            keys.extend(("announcement", item.announcement_id) for item in announcement_records)

        receipts = self.repository.list_notification_read_receipts(
            user_id=user_id,
            keys=tuple(keys),
        )

        for notification_record in notification_records:
            item_updated_at = float(notification_record.created_at or 0.0)
            receipt = receipts.get(("notification", notification_record.notification_id))
            read = bool(notification_record.read) if notification_record.user_id else self.receipt_covers(
                receipt, item_updated_at
            )
            items.append(
                {
                    "item_id": notification_record.notification_id,
                    "source": "notification",
                    "level": notification_record.level,
                    "category": notification_record.category,
                    "title": notification_record.title,
                    "content": notification_record.content,
                    "read": read,
                    "pinned": False,
                    "created_at": item_updated_at,
                    "updated_at": item_updated_at,
                    "expires_at": 0.0,
                }
            )

        for announcement_record in announcement_records:
            item_updated_at = float(announcement_record.updated_at or 0.0)
            receipt = receipts.get(("announcement", announcement_record.announcement_id))
            created_at = float(
                announcement_record.published_at
                or announcement_record.updated_at
                or announcement_record.created_at
            )
            items.append(
                {
                    "item_id": announcement_record.announcement_id,
                    "source": "announcement",
                    "level": announcement_record.level,
                    "category": "announcement",
                    "title": announcement_record.title,
                    "content": announcement_record.content,
                    "read": self.receipt_covers(receipt, item_updated_at),
                    "pinned": bool(announcement_record.pinned),
                    "created_at": created_at,
                    "updated_at": item_updated_at,
                    "expires_at": float(announcement_record.ends_at or 0.0),
                }
            )

        items.sort(key=lambda item: (not item["pinned"], -float(item["created_at"] or 0.0)))
        return items[: max(1, min(limit, 500))]

    @staticmethod
    def receipt_covers(
        receipt: NotificationReadReceiptRecord | None, item_updated_at: float
    ) -> bool:
        return bool(receipt and receipt.item_updated_at >= item_updated_at)

    @staticmethod
    def announcement_visible_for_role(
        record: AnnouncementRecord, *, role: str, now: float
    ) -> bool:
        return (
            record.status == "published"
            and record.audience in {"all", role}
            and (record.starts_at <= 0 or record.starts_at <= now)
            and (record.ends_at <= 0 or record.ends_at > now)
        )
