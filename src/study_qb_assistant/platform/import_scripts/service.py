"""导入脚本模板服务。"""

from __future__ import annotations

import secrets
import time
from threading import RLock
from typing import Any

from ...adapters.ocs.config import build_ocs_config_name
from ...auth import AuthError
from ..base import PlatformDomainService
from .templates import (
    get_import_script_template,
    load_import_script_templates,
    render_import_script,
)
from .records import ImportScriptRecord


class ImportScriptService(PlatformDomainService):
    """ImportScriptService 领域实现。"""

    def __init__(self, repository: Any, token_repository: Any, lock: RLock) -> None:
        super().__init__(repository, lock)
        self.token_repository = token_repository

    def list_import_scripts(self, *, platform_name: str) -> list[dict]:
        """列出全部导入脚本。"""
        builtin_scripts = []
        for template in load_import_script_templates():
            item = render_import_script(
                template,
                "",
                config_name=build_ocs_config_name(platform_name),
            )
            item["builtin"] = True
            item["status"] = "active"
            item["created_at"] = 0
            item["updated_at"] = 0
            builtin_scripts.append(item)
        with self.lock:
            custom_scripts = [item.to_dict() for item in self.repository.list_import_scripts()]
        return [*builtin_scripts, *custom_scripts]

    def get_import_script(
        self,
        script_id: str,
        *,
        base_url: str = "",
        platform_name: str,
    ) -> dict | None:
        """读取单个导入脚本。"""
        try:
            template = get_import_script_template(script_id)
        except KeyError:
            template = None
        if template is not None:
            payload = render_import_script(
                template,
                base_url,
                config_name=build_ocs_config_name(platform_name),
            )
            payload["builtin"] = True
            payload["status"] = "active"
            payload["created_at"] = 0
            payload["updated_at"] = 0
            return payload
        with self.lock:
            record = self.repository.get_import_script(script_id)
            if record is None:
                return None
            payload = record.to_dict()
            if base_url:
                payload["base_url"] = base_url
            return payload

    def create_import_script(
        self,
        *,
        name: str,
        target: str,
        content: str = "",
        description: str = "",
        script_template: str = "",
        config_items: tuple[dict, ...] | list[dict] = (),
        requires_token: bool = True,
        tags: tuple[str, ...] | list[str] = (),
        is_default: bool = False,
        status: str = "active",
        created_by: str = "",
    ) -> dict:
        """创建并保存导入脚本模板。"""
        now = time.time()
        script_content = content or script_template
        record = ImportScriptRecord(
            script_id=secrets.token_hex(12),
            name=(name or "导入脚本").strip(),
            integration_id=None,
            token_id=None,
            target=(target or "ocs").strip(),
            content=script_content,
            status=(status or "active").strip(),
            created_at=now,
            updated_at=now,
            description=description.strip(),
            requires_token=bool(requires_token),
            tags=tuple(str(item).strip() for item in tags if str(item).strip()),
            builtin=False,
            is_default=bool(is_default),
            ocs_config=tuple(dict(item) for item in config_items),
        )
        with self.lock:
            self.repository.save_import_script(record)
        return record.to_dict()

    def generate_import_script(
        self,
        *,
        name: str,
        token_id: str | None,
        target: str,
        include_test_snippet: bool,
    ) -> dict:
        """生成并保存导入脚本。"""
        token = self.token_repository.get_token(token_id) if token_id else None
        content_lines = [
            f"// {name or '导入脚本'}",
            f"// target: {target}",
        ]
        if token is not None:
            content_lines.append(f"const tokenId = '{token.token_id}';")
            content_lines.append(f"// token: {token.key_mask}")
        content_lines.append("export const config = { enabled: true };")
        if include_test_snippet:
            content_lines.append(
                "export function testConnection() { return Promise.resolve(true); }"
            )
        content = "\n".join(content_lines)
        now = time.time()
        record = ImportScriptRecord(
            script_id=secrets.token_hex(12),
            name=(name or "导入脚本").strip(),
            integration_id=None,
            token_id=token_id,
            target=(target or "ocs").strip(),
            content=content,
            status="active",
            created_at=now,
            updated_at=now,
            description=f"{name or '导入脚本'} 自动生成模板",
            requires_token=True,
            tags=("generated", target or "ocs"),
            builtin=False,
            is_default=False,
        )
        with self.lock:
            self.repository.save_import_script(record)
        return record.to_dict()

    def delete_import_script(self, script_id: str) -> bool:
        """删除导入脚本。"""
        try:
            get_import_script_template(script_id)
        except KeyError:
            pass
        else:
            raise AuthError("BUILTIN_SCRIPT_READONLY", "内置导入脚本不能删除", http_status=400)
        with self.lock:
            removed = self.repository.delete_import_script(script_id)
        if not removed:
            raise AuthError("SCRIPT_NOT_FOUND", "导入脚本不存在", http_status=404)
        return True
