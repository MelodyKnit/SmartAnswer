"""公开 Release 状态查询服务。

生产部署由 GitHub Actions 的受保护 Environment 完成。本模块只读取公开
Release，不保存 GitHub 凭据，不触发工作流，也不接触服务器或 Docker。
"""

from __future__ import annotations

import json
import re
import time
from threading import Lock, RLock
from typing import Any, Callable

from ...logger import log_event
from ...storage.repositories.settings import SettingsRepository
from ...version import BUILD_INFO, BuildInfo
from .contracts import (
    ProjectUpdateError,
    ProjectUpdateRelease,
    compare_versions,
    normalize_github_repository,
)
from .github import GitHubProjectUpdateGateway, ProjectUpdateGateway


UPDATE_STATE_SCOPE = "project_update_state"
LAST_CHECK_KEY = "last_check"
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LEGACY_PROJECT_UPDATE_SETTING_KEYS = {
    "project_update_enabled",
    "project_update_auto_check_enabled",
    "project_update_check_interval_hours",
    "project_update_repository",
    "project_update_workflow",
    "project_update_github_token",
}


class ProjectUpdateService:
    """维护当前构建与公开 GitHub Release 的比对状态。"""

    def __init__(
        self,
        repository: SettingsRepository,
        lock: RLock,
        *,
        gateway: ProjectUpdateGateway | None = None,
        build_info: BuildInfo = BUILD_INFO,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.repository = repository
        self.lock = lock
        self.gateway = gateway or GitHubProjectUpdateGateway()
        self.build_info = build_info
        self.clock = clock
        self.check_lock = Lock()

    def status(self) -> dict[str, Any]:
        """返回当前构建和最近一次公开 Release 检查结果。"""

        cached = self.load_json(LAST_CHECK_KEY)
        release = release_from_dict(cached.get("release"))
        repository = self.source_repository()
        latest_version = release.version if release is not None else ""
        has_update = bool(
            repository
            and self.build_info.build_type == "release"
            and latest_version
            and compare_versions(self.build_info.version, latest_version) < 0
        )
        error = str(cached.get("error") or "")[:1000]
        if not repository:
            state = "unavailable"
            message = "当前构建未声明公开来源仓库，无法检查 Release。"
        elif error:
            state = "failed"
            message = str(cached.get("message") or "最近一次 Release 检查失败。")
        else:
            state = "idle"
            message = str(cached.get("message") or "可检查公开 GitHub Release。")
        return {
            "available": bool(repository),
            "repository": repository,
            "current_version": self.build_info.version,
            "build_sha": self.build_info.build_sha,
            "build_type": self.build_info.build_type,
            "latest_version": latest_version,
            "has_update": has_update,
            "checked_at": safe_timestamp(cached.get("checked_at")),
            "state": state,
            "message": message,
            "error": error,
            "release": release.to_dict() if release is not None else None,
        }

    def check(self) -> dict[str, Any]:
        """立即查询并校验公开 GitHub Release。"""

        repository = self.require_source_repository()
        with self.check_lock:
            try:
                release = self.gateway.latest_release(repository)
            except ProjectUpdateError as exc:
                self.save_check(error=exc.message)
                log_event(
                    "project_release_check_failed",
                    {"repository": repository, "code": exc.code},
                )
                raise
            self.save_check(release=release)
            log_event(
                "project_release_checked",
                {"repository": repository, "version": release.version, "tag": release.tag},
            )
        return self.status()

    def source_repository(self) -> str:
        """读取镜像构建时注入的公开 GitHub 仓库标识。"""

        try:
            return normalize_github_repository(self.build_info.source_repository)
        except ValueError:
            return ""

    def require_source_repository(self) -> str:
        """确保当前构建可安全定位公开 Release。"""

        repository = self.source_repository()
        if not repository:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_SOURCE_UNAVAILABLE",
                "当前构建未配置公开 GitHub 仓库来源，无法检查更新",
                http_status=409,
            )
        return repository

    def save_check(
        self,
        *,
        release: ProjectUpdateRelease | None = None,
        error: str = "",
    ) -> None:
        """保存检查摘要；失败时保留最近一次已验证的 Release。"""

        with self.lock:
            previous = self.load_json(LAST_CHECK_KEY)
            payload: dict[str, Any] = {
                "checked_at": float(self.clock()),
                "message": (
                    "已检查公开 GitHub Release。"
                    if release is not None
                    else "公开 GitHub Release 检查失败。"
                ),
                "error": error[:1000],
            }
            if release is not None:
                payload["release"] = release.to_dict()
            elif isinstance(previous.get("release"), dict):
                payload["release"] = previous["release"]
            self.repository.set_settings(
                UPDATE_STATE_SCOPE,
                {LAST_CHECK_KEY: json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            )

    def load_json(self, key: str) -> dict[str, Any]:
        """读取损坏时自动降级为空的持久化检查状态。"""

        raw = self.repository.get_settings(UPDATE_STATE_SCOPE, keys={key}).get(key, "")
        if not raw or len(raw) > 32_000:
            return {}
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


def release_from_dict(value: object) -> ProjectUpdateRelease | None:
    """从持久化状态恢复经过基本格式验证的 Release 摘要。"""

    if not isinstance(value, dict):
        return None
    try:
        version = str(value.get("version") or "")
        compare_versions(version, version)
    except ValueError:
        return None
    image_digest = str(value.get("image_digest") or "")
    build_sha = str(value.get("build_sha") or "")
    if not IMAGE_DIGEST_RE.fullmatch(image_digest) or not COMMIT_SHA_RE.fullmatch(build_sha):
        return None
    return ProjectUpdateRelease(
        version=version,
        tag=str(value.get("tag") or ""),
        name=str(value.get("name") or "")[:200],
        body=str(value.get("body") or "")[:12000],
        published_at=str(value.get("published_at") or "")[:80],
        html_url=str(value.get("html_url") or "")[:1000],
        image=str(value.get("image") or "")[:300],
        image_digest=image_digest,
        build_sha=build_sha,
    )


def safe_timestamp(value: object) -> float:
    """读取非负时间戳。"""

    try:
        return max(0.0, float(str(value or "0")))
    except (TypeError, ValueError):
        return 0.0


def remove_legacy_project_update_settings(repository: SettingsRepository) -> None:
    """清除旧版本遗留的应用内更新配置和 GitHub 凭据。"""

    repository.delete_settings(
        "system_config", keys=LEGACY_PROJECT_UPDATE_SETTING_KEYS
    )
