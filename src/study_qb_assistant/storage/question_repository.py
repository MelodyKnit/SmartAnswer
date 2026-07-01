"""题库记录读取适配器。

当前题库主数据仍由 `LocalQuestionIndex` 管理。该模块为拆分后的 FastAPI
路由提供稳定 repository 形态，避免路由直接了解索引内部结构。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, or_, select

from ..models import CanonicalQuestionRecord
from ..normalization import normalize_text
from ..search import LocalQuestionIndex
from .database import get_session_factory
from .orm import QuestionEntity, SettingEntity


NON_ACTIVE_QUESTION_STATUSES = {"disabled", "deleted", "inactive"}
NON_INDEXABLE_QUESTION_STATUSES = NON_ACTIVE_QUESTION_STATUSES | {
    "low_confidence",
    "pending",
    "conflict",
}
SYNC_SETTINGS_SCOPE = "question_repository"
SYNC_SIGNATURE_KEY = "startup_index_signature"
SYNC_RECORD_COUNT_KEY = "startup_index_record_count"


@dataclass(frozen=True)
class QuestionIndexSyncResult:
    """题库启动同步结果，用于日志和启动诊断。"""

    record_count: int
    synced_count: int
    skipped: bool
    signature: str


class SqlAlchemyQuestionRepository:
    """基于 SQLAlchemy 的题库仓储。"""

    def __init__(self, path_or_url) -> None:
        self.session_factory = get_session_factory(path_or_url)

    def sync_from_index(self, index: LocalQuestionIndex) -> QuestionIndexSyncResult:
        """把启动时加载的 JSONL 内存索引同步到数据库题库表。"""

        signature = question_index_signature(index.records)
        record_count = len(index.records)
        with self.session_factory() as session:
            existing_signature = setting_value(
                session,
                scope=SYNC_SETTINGS_SCOPE,
                key=SYNC_SIGNATURE_KEY,
            )
            expected_count = setting_value(
                session,
                scope=SYNC_SETTINGS_SCOPE,
                key=SYNC_RECORD_COUNT_KEY,
            )
            existing_question_count = int(
                session.scalar(select(func.count()).select_from(QuestionEntity)) or 0
            )
            if (
                existing_signature == signature
                and existing_question_count >= json_int(expected_count)
            ):
                return QuestionIndexSyncResult(
                    record_count=record_count,
                    synced_count=0,
                    skipped=True,
                    signature=signature,
                )

        with self.session_factory() as session:
            deleted_ids = set(
                session.scalars(
                    select(QuestionEntity.question_id).where(
                        or_(
                            QuestionEntity.status == "deleted",
                            QuestionEntity.record_status == "deleted",
                        )
                    )
                ).all()
            )
            existing_entities = {
                entity.question_id: entity
                for entity in session.scalars(select(QuestionEntity)).all()
            }
            synced = 0
            now = time.time()
            for record in index.records:
                if record.question_id in deleted_ids:
                    continue
                entity = existing_entities.get(record.question_id)
                if entity is None:
                    entity = QuestionEntity(question_id=record.question_id, created_at=now)
                    session.add(entity)
                self._apply_record_to_entity(entity, record, updated_at=now)
                synced += 1
            set_setting_value(
                session,
                scope=SYNC_SETTINGS_SCOPE,
                key=SYNC_SIGNATURE_KEY,
                value=signature,
            )
            set_setting_value(
                session,
                scope=SYNC_SETTINGS_SCOPE,
                key=SYNC_RECORD_COUNT_KEY,
                value=str(record_count),
            )
            session.commit()
        return QuestionIndexSyncResult(
            record_count=record_count,
            synced_count=synced,
            skipped=False,
            signature=signature,
        )

    def list_all_active_records(self) -> list[CanonicalQuestionRecord]:
        """返回所有未禁用题目。"""

        with self.session_factory() as session:
            entities = session.scalars(
                select(QuestionEntity).order_by(QuestionEntity.updated_at.desc())
            ).all()
            return [
                self._record_from_entity(entity)
                for entity in entities
                if question_entity_status(entity) not in NON_ACTIVE_QUESTION_STATUSES
            ]

    def list_indexable_records(self) -> list[CanonicalQuestionRecord]:
        """返回允许进入本地命中索引的可信题目。"""

        with self.session_factory() as session:
            entities = session.scalars(
                select(QuestionEntity).order_by(QuestionEntity.updated_at.desc())
            ).all()
            return [
                self._record_from_entity(entity)
                for entity in entities
                if question_status_is_indexable(question_entity_status(entity))
            ]

    def count_questions(
        self,
        *,
        keyword: str = "",
        question_type: str = "",
        source_name: str = "",
        status: str = "",
        is_active: bool = True,
        updated_start_time: float | None = None,
        updated_end_time: float | None = None,
    ) -> int:
        """统计符合筛选条件的题目数量。"""

        with self.session_factory() as session:
            stmt = select(func.count()).select_from(QuestionEntity)
            stmt = self._apply_filters(
                stmt,
                keyword=keyword,
                question_type=question_type,
                source_name=source_name,
                status=status,
                is_active=is_active,
                updated_start_time=updated_start_time,
                updated_end_time=updated_end_time,
            )
            return int(session.scalar(stmt) or 0)

    def list_question_records(
        self,
        *,
        keyword: str = "",
        question_type: str = "",
        source_name: str = "",
        status: str = "",
        is_active: bool = True,
        updated_start_time: float | None = None,
        updated_end_time: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CanonicalQuestionRecord]:
        """分页读取符合筛选条件的题目。"""

        with self.session_factory() as session:
            stmt = select(QuestionEntity).order_by(QuestionEntity.updated_at.desc())
            stmt = self._apply_filters(
                stmt,
                keyword=keyword,
                question_type=question_type,
                source_name=source_name,
                status=status,
                is_active=is_active,
                updated_start_time=updated_start_time,
                updated_end_time=updated_end_time,
            )
            entities = session.scalars(
                stmt.offset(max(0, int(offset))).limit(max(1, min(int(limit), 500)))
            ).all()
            return [self._record_from_entity(entity) for entity in entities]

    def question_types(self) -> list[str]:
        """返回题型集合。"""

        with self.session_factory() as session:
            rows = session.scalars(select(QuestionEntity.question_type).distinct()).all()
            return sorted({str(item) for item in rows if item})

    def source_names(self) -> list[str]:
        """返回来源集合。"""

        with self.session_factory() as session:
            rows = session.scalars(select(QuestionEntity.source_name).distinct()).all()
            return sorted({str(item) for item in rows if item})

    def get_question_record(self, question_id: str) -> CanonicalQuestionRecord | None:
        """按题目 ID 读取记录。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(QuestionEntity).where(QuestionEntity.question_id == question_id)
            )
            return self._record_from_entity(entity) if entity is not None else None

    def save_question_record(self, record: CanonicalQuestionRecord) -> None:
        """新增或更新题库记录。"""

        now = time.time()
        with self.session_factory() as session:
            entity = session.scalar(
                select(QuestionEntity).where(QuestionEntity.question_id == record.question_id)
            )
            if entity is None:
                entity = QuestionEntity(question_id=record.question_id, created_at=now)
                session.add(entity)
            self._apply_record_to_entity(entity, record, updated_at=now)
            session.commit()

    def soft_delete_question_record(self, question_id: str) -> CanonicalQuestionRecord | None:
        """软删除题库记录，并保留数据库审计数据。"""

        now = time.time()
        with self.session_factory() as session:
            entity = session.scalar(
                select(QuestionEntity).where(QuestionEntity.question_id == question_id)
            )
            if entity is None:
                return None
            metadata = json_object(entity.metadata_json, default={})
            metadata["status"] = "deleted"
            metadata["updated_at"] = str(now)
            metadata.setdefault("created_at", str(float(entity.created_at or 0.0) or now))
            metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            entity.metadata_json = metadata_text
            entity.legacy_metadata_json = metadata_text
            entity.status = "deleted"
            entity.record_status = "deleted"
            entity.is_active = 0
            entity.review_required = 0
            entity.updated_at = now
            session.commit()
            return self._record_from_entity(entity)

    def _apply_filters(
        self,
        stmt,
        *,
        keyword: str,
        question_type: str,
        source_name: str,
        status: str,
        is_active: bool,
        updated_start_time: float | None,
        updated_end_time: float | None,
    ):
        normalized_keyword = keyword.strip()
        normalized_type = question_type.strip()
        normalized_source = source_name.strip()
        normalized_status = status.strip()
        if is_active:
            stmt = stmt.where(~QuestionEntity.status.in_(NON_ACTIVE_QUESTION_STATUSES))
        if normalized_type:
            stmt = stmt.where(QuestionEntity.question_type == normalized_type)
        if normalized_source:
            stmt = stmt.where(QuestionEntity.source_name == normalized_source)
        if normalized_status:
            stmt = stmt.where(QuestionEntity.status == normalized_status)
        if updated_start_time is not None:
            stmt = stmt.where(QuestionEntity.updated_at >= updated_start_time)
        if updated_end_time is not None:
            stmt = stmt.where(QuestionEntity.updated_at < updated_end_time)
        if normalized_keyword:
            like = f"%{normalized_keyword}%"
            stmt = stmt.where(
                or_(
                    QuestionEntity.title_raw.contains(normalized_keyword),
                    QuestionEntity.options_raw.like(like),
                    QuestionEntity.answer_raw.contains(normalized_keyword),
                    QuestionEntity.explanation.contains(normalized_keyword),
                    QuestionEntity.source_name.contains(normalized_keyword),
                    QuestionEntity.tags.like(like),
                    QuestionEntity.metadata_json.like(like),
                    QuestionEntity.legacy_metadata_json.like(like),
                )
            )
        return stmt

    def _apply_record_to_entity(
        self,
        entity: QuestionEntity,
        record: CanonicalQuestionRecord,
        *,
        updated_at: float,
    ) -> None:
        metadata = dict(record.metadata)
        status = question_record_status(record)
        confidence = question_record_confidence(record)
        metadata["status"] = status
        metadata["confidence"] = str(confidence)
        metadata.setdefault("created_at", str(getattr(entity, "created_at", 0.0) or updated_at))
        metadata["updated_at"] = str(updated_at)
        entity.title_raw = record.title_raw
        entity.question_type = record.question_type
        entity.options_raw = json.dumps(list(record.options_raw), ensure_ascii=False)
        entity.answer_raw = record.answer_raw
        entity.explanation = record.explanation
        entity.subject = record.subject
        entity.chapter = record.chapter
        entity.tags = json.dumps(list(record.tags), ensure_ascii=False)
        entity.source_name = record.source_name
        entity.source_url = record.source_url
        entity.source_license = record.source_license
        entity.source_split = record.source_split
        entity.source_record_path = record.source_record_path
        entity.passage = record.passage
        metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        entity.metadata_json = metadata_text
        entity.status = status
        entity.confidence = confidence
        entity.updated_at = updated_at
        # 兼容早期数据库表中的 NOT NULL 字段，避免旧运行库阻断新题入库。
        entity.title_normalized = normalize_text(record.title_raw)
        entity.legacy_metadata_json = metadata_text
        entity.origin_kind = str(metadata.get("origin_kind") or metadata.get("origin") or "")
        entity.record_status = status
        entity.provider_name = str(metadata.get("provider") or "")
        entity.confirmations = json_int(metadata.get("confirmations"))
        entity.conflicts = json_int(metadata.get("conflicts"))
        entity.review_required = 1 if status in {"low_confidence", "pending", "conflict"} else 0
        entity.is_active = 0 if status in NON_ACTIVE_QUESTION_STATUSES else 1

    def _record_from_entity(self, entity: QuestionEntity) -> CanonicalQuestionRecord:
        metadata = json_object(entity.metadata_json, default={})
        legacy_metadata = str(entity.legacy_metadata_json or "")
        if not metadata and legacy_metadata:
            metadata = json_object(legacy_metadata, default={})
        status = question_entity_status(entity)
        metadata["status"] = status
        metadata["confidence"] = str(float(entity.confidence or 0.0))
        metadata["created_at"] = str(float(entity.created_at or 0.0))
        metadata["updated_at"] = str(float(entity.updated_at or 0.0))
        return CanonicalQuestionRecord(
            question_id=entity.question_id,
            title_raw=entity.title_raw,
            question_type=entity.question_type,
            options_raw=tuple(json_list(entity.options_raw)),
            answer_raw=entity.answer_raw,
            explanation=entity.explanation,
            subject=entity.subject,
            chapter=entity.chapter,
            tags=tuple(json_list(entity.tags)),
            source_name=entity.source_name,
            source_url=entity.source_url,
            source_license=entity.source_license,
            source_split=entity.source_split,
            source_record_path=entity.source_record_path,
            passage=entity.passage,
            metadata={str(key): str(value) for key, value in metadata.items()},
        )


class IndexQuestionRepository:
    """基于 `LocalQuestionIndex` 的题库管理适配器。"""

    def __init__(self, index: LocalQuestionIndex) -> None:
        self.index = index

    def list_all_active_records(self) -> list[CanonicalQuestionRecord]:
        """返回当前索引中的全部启用题目。"""

        return list(self.index.records)

    def list_indexable_records(self) -> list[CanonicalQuestionRecord]:
        """返回允许进入本地命中索引的可信题目。"""

        return [
            record
            for record in self.index.records
            if question_status_is_indexable(question_record_status(record))
        ]

    def count_questions(
        self,
        *,
        keyword: str = "",
        question_type: str = "",
        source_name: str = "",
        status: str = "",
        is_active: bool = True,
        updated_start_time: float | None = None,
        updated_end_time: float | None = None,
    ) -> int:
        """统计符合筛选条件的题目数量。"""

        return len(
            self._filter_records(
                keyword=keyword,
                question_type=question_type,
                source_name=source_name,
                status=status,
                is_active=is_active,
                updated_start_time=updated_start_time,
                updated_end_time=updated_end_time,
            )
        )

    def list_question_records(
        self,
        *,
        keyword: str = "",
        question_type: str = "",
        source_name: str = "",
        status: str = "",
        is_active: bool = True,
        updated_start_time: float | None = None,
        updated_end_time: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CanonicalQuestionRecord]:
        """分页读取符合筛选条件的题目。"""

        records = self._filter_records(
            keyword=keyword,
            question_type=question_type,
            source_name=source_name,
            status=status,
            is_active=is_active,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
        )
        start = max(0, int(offset))
        end = start + max(1, min(int(limit), 500))
        return records[start:end]

    def question_types(self) -> list[str]:
        """返回索引中的题型集合。"""

        return sorted(
            {record.question_type for record in self.index.records if record.question_type}
        )

    def source_names(self) -> list[str]:
        """返回索引中的来源集合。"""

        return sorted({record.source_name for record in self.index.records if record.source_name})

    def get_question_record(self, question_id: str) -> CanonicalQuestionRecord | None:
        """按题目 ID 读取记录。"""

        for record in self.index.records:
            if record.question_id == question_id:
                return record
        return None

    def save_question_record(self, record: CanonicalQuestionRecord) -> None:
        """保存题目记录到当前索引。"""

        self.index.add_or_replace(record)

    def soft_delete_question_record(self, question_id: str) -> CanonicalQuestionRecord | None:
        """从当前索引中软删除题目记录。"""

        target = self.get_question_record(question_id)
        if target is None:
            return None
        payload = target.to_dict()
        metadata = dict(target.metadata)
        metadata["status"] = "deleted"
        metadata["updated_at"] = str(time.time())
        payload["metadata"] = metadata
        payload["source_split"] = "deleted"
        deleted_record = CanonicalQuestionRecord.from_dict(payload)
        self.index.remove(question_id)
        return deleted_record

    def _filter_records(
        self,
        *,
        keyword: str,
        question_type: str,
        source_name: str,
        status: str,
        is_active: bool,
        updated_start_time: float | None,
        updated_end_time: float | None,
    ) -> list[CanonicalQuestionRecord]:
        normalized_keyword = normalize_text(keyword)
        normalized_type = question_type.strip()
        normalized_source = source_name.strip()
        normalized_status = status.strip()
        records: Iterable[CanonicalQuestionRecord] = self.index.records
        filtered: list[CanonicalQuestionRecord] = []
        for record in records:
            record_status = question_record_status(record)
            if is_active and record_status in NON_ACTIVE_QUESTION_STATUSES:
                continue
            if normalized_type and record.question_type != normalized_type:
                continue
            if normalized_source and record.source_name != normalized_source:
                continue
            if normalized_status and record_status != normalized_status:
                continue
            updated_at = record.to_dict().get("updated_at") or 0
            if updated_start_time is not None and float(updated_at) < updated_start_time:
                continue
            if updated_end_time is not None and float(updated_at) >= updated_end_time:
                continue
            searchable = " ".join(
                (
                    record.title_raw,
                    " ".join(record.options_raw),
                    record.answer_raw or "",
                    record.explanation or "",
                    record.source_name,
                    " ".join(record.tags),
                    " ".join(str(value) for value in record.metadata.values()),
                )
            )
            if normalized_keyword and normalized_keyword not in normalize_text(searchable):
                continue
            filtered.append(record)
        return filtered


def question_record_status(record: CanonicalQuestionRecord) -> str:
    """从标准题库记录中提取统一状态。"""

    return str(
        record.metadata.get("status")
        or record.metadata.get("ai_status")
        or record.source_split
        or "active"
    )


def question_status_is_indexable(status: str) -> bool:
    """判断某个题库状态是否允许参与自动命中。"""

    normalized = str(status or "active").strip().casefold() or "active"
    return normalized not in NON_INDEXABLE_QUESTION_STATUSES


def question_entity_status(entity: QuestionEntity) -> str:
    """从数据库实体中恢复更有语义的题库状态。"""

    preferred = (
        str(getattr(entity, "record_status", "") or "").strip(),
        str(getattr(entity, "status", "") or "").strip(),
        str(getattr(entity, "source_split", "") or "").strip(),
    )
    for value in preferred:
        lowered = value.casefold()
        if lowered and lowered not in {"active", "default", "normal"}:
            return value
    for value in preferred:
        if value:
            return value
    return "active"


def question_record_confidence(record: CanonicalQuestionRecord) -> float:
    """从题库记录中提取统一置信度。"""

    raw = record.metadata.get("confidence") or record.metadata.get("ai_confidence") or "0"
    try:
        return float(str(raw))
    except (TypeError, ValueError):
        return 0.0


def question_index_signature(records: Iterable[CanonicalQuestionRecord]) -> str:
    """计算启动题库内容签名，避免热重载时重复全量写库。"""

    digest = hashlib.sha256()
    count = 0
    for record in records:
        count += 1
        payload = {
            "question_id": record.question_id,
            "title_raw": record.title_raw,
            "question_type": record.question_type,
            "options_raw": list(record.options_raw),
            "answer_raw": record.answer_raw,
            "explanation": record.explanation,
            "subject": record.subject,
            "chapter": record.chapter,
            "tags": list(record.tags),
            "source_name": record.source_name,
            "source_split": record.source_split,
            "source_record_path": record.source_record_path,
            "metadata": dict(record.metadata),
        }
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    digest.update(f"count={count}".encode("ascii"))
    return digest.hexdigest()


def setting_value(session, *, scope: str, key: str) -> str:
    """读取仓储私有设置值。"""

    entity = session.scalar(
        select(SettingEntity).where(SettingEntity.scope == scope, SettingEntity.key == key)
    )
    return str(entity.value) if entity is not None else ""


def set_setting_value(session, *, scope: str, key: str, value: str) -> None:
    """写入仓储私有设置值。"""

    entity = session.scalar(
        select(SettingEntity).where(SettingEntity.scope == scope, SettingEntity.key == key)
    )
    if entity is None:
        session.add(SettingEntity(scope=scope, key=key, value=value))
        return
    entity.value = value


def json_list(payload: str | None) -> list[str]:
    """安全解析 JSON 字符串列表。"""

    try:
        decoded = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def json_object(payload: str | None, *, default: dict[str, object]) -> dict[str, object]:
    """安全解析 JSON 字符串对象。"""

    try:
        decoded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return dict(default)
    if not isinstance(decoded, dict):
        return dict(default)
    return dict(decoded)


def json_int(value: object) -> int:
    """把 JSON 元数据中的数字字段安全转换为整数。"""

    try:
        return int(float(str(value or "0")))
    except (TypeError, ValueError):
        return 0
