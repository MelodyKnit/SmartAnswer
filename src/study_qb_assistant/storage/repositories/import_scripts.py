"""导入脚本仓储。"""

from __future__ import annotations

import json

from sqlalchemy import select

from ...platform.import_scripts.records import ImportScriptRecord
from ..orm import ImportScriptEntity
from .base import SqlAlchemyRepository


class ImportScriptRepository(SqlAlchemyRepository):
    """ImportScriptRepository 实现。"""

    def save_import_script(self, record: ImportScriptRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == record.script_id)
            )
            if entity is None:
                entity = ImportScriptEntity(script_id=record.script_id)
                session.add(entity)
            self._apply_import_script(entity, record)
            session.commit()

    def list_import_scripts(self) -> list[ImportScriptRecord]:
        with self.session_factory() as session:
            entities = session.scalars(
                select(ImportScriptEntity).order_by(ImportScriptEntity.created_at.desc())
            ).all()
            return [self._import_script_record(entity) for entity in entities]

    def get_import_script(self, script_id: str) -> ImportScriptRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id)
            )
            return self._import_script_record(entity) if entity else None

    def delete_import_script(self, script_id: str) -> bool:
        with self.session_factory() as session:
            entity = session.scalar(
                select(ImportScriptEntity).where(ImportScriptEntity.script_id == script_id)
            )
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def _apply_import_script(self, entity: ImportScriptEntity, record: ImportScriptRecord) -> None:
        entity.script_id = record.script_id
        entity.name = record.name
        entity.integration_id = record.integration_id
        entity.token_id = record.token_id
        entity.target = record.target
        entity.content = record.content
        entity.status = record.status
        entity.created_at = record.created_at
        entity.updated_at = record.updated_at
        entity.description = record.description
        entity.requires_token = 1 if record.requires_token else 0
        entity.tags = json.dumps(list(record.tags), ensure_ascii=False)
        entity.builtin = 1 if record.builtin else 0
        entity.is_default = 1 if record.is_default else 0
        entity.ocs_config = json.dumps(list(record.ocs_config), ensure_ascii=False)

    def _import_script_record(self, entity: ImportScriptEntity) -> ImportScriptRecord:
        return ImportScriptRecord(
            script_id=entity.script_id,
            name=entity.name,
            integration_id=entity.integration_id,
            token_id=entity.token_id,
            target=entity.target,
            content=entity.content,
            status=entity.status,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            description=getattr(entity, "description", "") or "",
            requires_token=bool(getattr(entity, "requires_token", 1)),
            tags=tuple(json.loads(getattr(entity, "tags", "[]") or "[]")),
            builtin=bool(getattr(entity, "builtin", 0)),
            is_default=bool(getattr(entity, "is_default", 0)),
            ocs_config=tuple(json.loads(getattr(entity, "ocs_config", "[]") or "[]")),
        )
