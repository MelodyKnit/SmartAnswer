"""应用内项目更新控制面。

该服务只查询 GitHub Release 并调度 GitHub Actions；它不执行 shell、不访问 Docker
Socket，也不持有服务器 SSH 凭据。实际部署仍由仓库内受保护的工作流完成。
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import replace
from threading import Lock, RLock
from typing import Any, Callable

from ...logger import log_event
from ...storage.repositories.settings import SettingsRepository
from ...version import BUILD_INFO, BuildInfo
from ..settings import SettingsService
from .contracts import (
    ProjectUpdateConfiguration,
    ProjectUpdateError,
    ProjectUpdateOperation,
    ProjectUpdateRelease,
    compare_versions,
    normalize_version,
    valid_operation_id,
)
from .github import GitHubProjectUpdateGateway, ProjectUpdateGateway


UPDATE_STATE_SCOPE = "project_update_state"
LAST_CHECK_KEY = "last_check"
LAST_OPERATION_KEY = "last_operation"
ACTIVE_STATES = frozenset({"queued", "running"})
WORKFLOW_START_TIMEOUT_SECONDS = 10 * 60


class ProjectUpdateService:
    """协调更新配置、GitHub Release 检查、巡检与部署任务轮询。"""

    def __init__(
        self,
        repository: SettingsRepository,
        settings: SettingsService,
        lock: RLock,
        *,
        gateway: ProjectUpdateGateway | None = None,
        build_info: BuildInfo = BUILD_INFO,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.lock = lock
        self.gateway = gateway or GitHubProjectUpdateGateway()
        self.build_info = build_info
        self.clock = clock
        self.check_lock = Lock()
        self.operation_lock = Lock()

    def status(self) -> dict[str, Any]:
        """返回缓存的 Release 检查结果与当前部署版本。"""

        config = self.update_config()
        cached = self.load_json(LAST_CHECK_KEY)
        operation = self.load_operation()
        release = release_from_dict(cached.get("release"))
        latest_version = release.version if release is not None else ""
        current_version = self.build_info.version
        checked_at = safe_timestamp(cached.get("checked_at"))
        has_update = bool(
            config.configured
            and current_version != "dev"
            and latest_version
            and compare_versions(current_version, latest_version) < 0
        )
        next_check_at = 0.0
        if config.enabled and config.configured and config.automatic_check_enabled:
            next_check_at = checked_at + config.check_interval_seconds if checked_at else float(self.clock())

        if operation is not None and operation.state in ACTIVE_STATES:
            state = operation.state
            message = operation.message
        elif not config.enabled:
            state = "disabled"
            message = "项目内更新尚未启用。"
        elif not config.configured:
            state = "unconfigured"
            message = "请先填写 GitHub 仓库、访问令牌和部署工作流，再启用项目更新。"
        elif operation is not None:
            state = operation.state
            message = operation.message
        else:
            state = "idle"
            message = str(cached.get("message") or "可检查 GitHub Release 更新")
        return {
            "configured": config.configured,
            "enabled": config.enabled,
            "automatic_check_enabled": config.automatic_check_enabled,
            "check_interval_hours": config.check_interval_hours,
            "next_check_at": next_check_at,
            "repository": config.repository,
            "workflow": config.workflow,
            "current_version": current_version,
            "build_sha": self.build_info.build_sha,
            "build_type": self.build_info.build_type,
            "latest_version": latest_version,
            "has_update": has_update,
            "checked_at": checked_at,
            "state": state,
            "message": message,
            "error": str(cached.get("error") or "")[:1000],
            "release": release.to_dict() if release is not None else None,
            "operation": operation.to_dict() if operation is not None else None,
        }

    def check(self, *, source: str = "manual") -> dict[str, Any]:
        """立即从 GitHub 查询并校验最新正式 Release。"""

        config = self.require_enabled_configuration()
        with self.check_lock:
            try:
                release = self.gateway.latest_release(config.repository, config.token)
            except ProjectUpdateError as exc:
                self.save_check(error=exc.message)
                log_event(
                    "project_update_check_failed",
                    {"repository": config.repository, "code": exc.code, "source": source},
                )
                raise
            self.save_check(release=release)
            log_event(
                "project_update_checked",
                {
                    "repository": config.repository,
                    "version": release.version,
                    "tag": release.tag,
                    "source": source,
                },
            )
        return self.status()

    def apply(self, *, expected_version: str, requested_by: str) -> ProjectUpdateOperation:
        """调度 GitHub Actions 部署管理员确认的正式 Release。"""

        with self.operation_lock:
            config = self.require_enabled_configuration()
            if self.build_info.build_type != "release":
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_SOURCE_BUILD",
                    "当前为本地源码运行，不能通过线上发布流程覆盖更新",
                    http_status=409,
                )
            try:
                target_version = normalize_version(expected_version)
            except ValueError as exc:
                raise ProjectUpdateError("INVALID_INPUT", str(exc), http_status=400) from exc

            existing = self.refresh_active_operation(config)
            if existing is not None and existing.state in ACTIVE_STATES:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_IN_PROGRESS",
                    "已有项目更新任务正在执行，请等待其完成",
                    http_status=409,
                )

            checked = self.check()
            release = release_from_dict(checked.get("release"))
            if release is None or not checked["has_update"]:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_NOT_AVAILABLE",
                    "当前没有可部署的新版本，请先完成检查更新",
                    http_status=409,
                )
            if release.version != target_version:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_VERSION_CHANGED",
                    "最新版本已变化，请重新确认后再更新",
                    http_status=409,
                )

            now = float(self.clock())
            operation = ProjectUpdateOperation(
                operation_id=secrets.token_hex(16),
                expected_version=release.version,
                requested_by=safe_requested_by(requested_by),
                state="queued",
                created_at=now,
                updated_at=now,
                message="已提交 GitHub Actions 部署任务，等待工作流接收。",
            )
            self.save_operation(operation)
            try:
                self.gateway.dispatch_deployment(
                    config.repository,
                    config.workflow,
                    config.token,
                    release_tag=release.tag,
                    operation_id=operation.operation_id,
                )
            except ProjectUpdateError as exc:
                failed = replace(
                    operation,
                    state="failed",
                    updated_at=float(self.clock()),
                    message="GitHub Actions 部署任务提交失败。",
                    error=exc.message,
                )
                self.save_operation(failed)
                log_event(
                    "project_update_dispatch_failed",
                    {"repository": config.repository, "code": exc.code},
                )
                raise
            log_event(
                "project_update_dispatched",
                {
                    "repository": config.repository,
                    "operation_id": operation.operation_id,
                    "expected_version": release.version,
                    "requested_by": operation.requested_by,
                },
            )
            return operation

    def operation(self, operation_id: str) -> ProjectUpdateOperation:
        """读取并刷新指定的项目更新任务状态。"""

        expected_id = valid_operation_id(operation_id)
        if not expected_id:
            raise ProjectUpdateError("INVALID_INPUT", "更新任务 ID 格式不正确", http_status=400)
        with self.operation_lock:
            operation = self.load_operation()
            if operation is None or operation.operation_id != expected_id:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_OPERATION_NOT_FOUND",
                    "项目更新任务不存在或已被新的任务替代",
                    http_status=404,
                )
            if operation.state not in ACTIVE_STATES:
                return operation
            refreshed = self.refresh_active_operation(self.require_credential_configuration(), operation)
            return refreshed or operation

    def background_cycle(self) -> None:
        """执行一次轻量巡检：恢复活动任务，并在到期时检查新 Release。"""

        config = self.update_config()
        if config.configured:
            try:
                with self.operation_lock:
                    self.refresh_active_operation(config)
            except ProjectUpdateError as exc:
                log_event(
                    "project_update_operation_poll_failed",
                    {"repository": config.repository, "code": exc.code},
                )

        if not (config.enabled and config.configured and config.automatic_check_enabled):
            return
        if not self.check_is_due(config):
            return
        try:
            self.check(source="automatic")
        except ProjectUpdateError:
            # check() 已保存错误摘要和日志；后台巡检不能因为单次网络错误退出。
            return

    def clear_access_token(self) -> dict[str, Any]:
        """在停用更新且没有活动部署时清除 GitHub 访问令牌。"""

        with self.operation_lock:
            config = self.update_config()
            operation = self.load_operation()
            if operation is not None and operation.state in ACTIVE_STATES:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_IN_PROGRESS",
                    "部署任务仍在执行，暂时不能清除 GitHub 访问令牌",
                    http_status=409,
                )
            if config.enabled:
                raise ProjectUpdateError(
                    "PROJECT_UPDATE_ENABLED",
                    "请先关闭并保存项目更新，再清除 GitHub 访问令牌",
                    http_status=409,
                )
            self.settings.clear_system_secret("project_update_github_token")
        log_event("project_update_token_cleared", {"repository": config.repository})
        return self.settings.get_system_config()

    def update_config(self) -> ProjectUpdateConfiguration:
        """读取项目更新配置，并避免向调用者暴露 GitHub 令牌。"""

        raw = self.settings.get_system_config(reveal_secret=True)
        enabled = is_enabled(raw.get("project_update_enabled"))
        repository = str(raw.get("project_update_repository") or "").strip()
        workflow = str(raw.get("project_update_workflow") or "").strip()
        token = str(raw.get("project_update_github_token") or "").strip()
        automatic_check_enabled = is_enabled(raw.get("project_update_auto_check_enabled"))
        check_interval_hours = safe_check_interval(raw.get("project_update_check_interval_hours"))
        return ProjectUpdateConfiguration(
            enabled=enabled,
            configured=bool(repository and workflow and token),
            automatic_check_enabled=automatic_check_enabled,
            check_interval_hours=check_interval_hours,
            repository=repository,
            workflow=workflow,
            token=token,
        )

    def require_enabled_configuration(self) -> ProjectUpdateConfiguration:
        """确保项目更新已启用且具备私有仓库访问配置。"""

        config = self.require_credential_configuration()
        if not config.enabled:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_DISABLED",
                "项目内更新尚未启用，请先保存并开启项目更新配置",
                http_status=409,
            )
        return config

    def require_credential_configuration(self) -> ProjectUpdateConfiguration:
        """确保任务轮询或检查拥有可用的 GitHub 私有仓库凭据。"""

        config = self.update_config()
        if not config.configured:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_UNCONFIGURED",
                "请先填写 GitHub 仓库、访问令牌和部署工作流",
                http_status=409,
            )
        return config

    def check_is_due(self, config: ProjectUpdateConfiguration) -> bool:
        """判断自动检查是否已到期；首次启动会立即检查一次。"""

        checked_at = safe_timestamp(self.load_json(LAST_CHECK_KEY).get("checked_at"))
        return not checked_at or float(self.clock()) >= checked_at + config.check_interval_seconds

    def refresh_active_operation(
        self,
        config: ProjectUpdateConfiguration,
        operation: ProjectUpdateOperation | None = None,
    ) -> ProjectUpdateOperation | None:
        """同步活动工作流状态，并回收长期未创建的调度任务。"""

        current = operation or self.load_operation()
        if current is None or current.state not in ACTIVE_STATES:
            return current

        now = float(self.clock())
        run: dict[str, Any] | None
        if current.workflow_run_id:
            run = self.gateway.get_deployment_run(
                config.repository,
                config.token,
                current.workflow_run_id,
            )
        else:
            run = self.gateway.find_deployment_run(
                config.repository,
                config.workflow,
                config.token,
                current.operation_id,
            )

        if run is None:
            if now - current.created_at >= WORKFLOW_START_TIMEOUT_SECONDS:
                failed = replace(
                    current,
                    state="failed",
                    updated_at=now,
                    last_polled_at=now,
                    message="GitHub Actions 未在预期时间内创建部署任务。",
                    error="PROJECT_UPDATE_WORKFLOW_NOT_STARTED",
                )
                self.save_operation(failed)
                log_event(
                    "project_update_workflow_timeout",
                    {"operation_id": current.operation_id, "repository": config.repository},
                )
                return failed
            pending = replace(current, last_polled_at=now)
            self.save_operation(pending)
            return pending

        refreshed = operation_from_workflow_run(current, run, now)
        self.save_operation(refreshed)
        if refreshed.state in {"succeeded", "failed"}:
            log_event(
                "project_update_finished",
                {
                    "operation_id": refreshed.operation_id,
                    "expected_version": refreshed.expected_version,
                    "state": refreshed.state,
                },
            )
        return refreshed

    def load_operation(self) -> ProjectUpdateOperation | None:
        """读取最后一次项目更新任务。"""

        return operation_from_dict(self.load_json(LAST_OPERATION_KEY))

    def save_operation(self, operation: ProjectUpdateOperation) -> None:
        """持久化当前更新任务，供容器重启后的后台巡检继续恢复。"""

        with self.lock:
            self.repository.set_settings(
                UPDATE_STATE_SCOPE,
                {LAST_OPERATION_KEY: json.dumps(operation.to_dict(), ensure_ascii=False)},
            )

    def save_check(
        self,
        *,
        release: ProjectUpdateRelease | None = None,
        error: str = "",
    ) -> None:
        """缓存最后检查时间和经验证的 Release 摘要。"""

        payload: dict[str, Any] = {
            "checked_at": float(self.clock()),
            "message": "已从 GitHub 检查最新正式 Release" if release else "GitHub 更新检查失败",
            "error": error[:1000],
        }
        if release is not None:
            payload["release"] = release.to_dict()
        elif previous_release := self.load_json(LAST_CHECK_KEY).get("release"):
            # 保留上次已经通过 manifest 校验的版本。更新操作仍会再次校验，
            # 因此临时网络故障不会把可信候选版本变成可直接部署的未验证数据。
            payload["release"] = previous_release
        with self.lock:
            self.repository.set_settings(
                UPDATE_STATE_SCOPE,
                {LAST_CHECK_KEY: json.dumps(payload, ensure_ascii=False)},
            )

    def load_json(self, key: str) -> dict[str, Any]:
        """读取受限的内部 JSON 状态，损坏状态按空处理。"""

        raw = self.repository.get_settings(UPDATE_STATE_SCOPE, keys={key}).get(key, "")
        if not raw or len(raw) > 32_000:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


def release_from_dict(payload: object) -> ProjectUpdateRelease | None:
    """从持久化检查缓存恢复已经校验过的 Release 摘要。"""

    if not isinstance(payload, dict):
        return None
    try:
        return ProjectUpdateRelease(
            version=normalize_version(payload.get("version")),
            tag=str(payload.get("tag") or "")[:80],
            name=str(payload.get("name") or "")[:200],
            body=str(payload.get("body") or "")[:12000],
            published_at=str(payload.get("published_at") or "")[:80],
            html_url=str(payload.get("html_url") or "")[:1000],
            image=str(payload.get("image") or "")[:300],
            image_digest=str(payload.get("image_digest") or "")[:100],
            build_sha=str(payload.get("build_sha") or "")[:40],
        )
    except ValueError:
        return None


def operation_from_dict(payload: object) -> ProjectUpdateOperation | None:
    """从持久化状态恢复结构化更新任务。"""

    if not isinstance(payload, dict):
        return None
    operation_id = valid_operation_id(payload.get("operation_id"))
    state = str(payload.get("state") or "")
    if not operation_id or state not in {
        "queued",
        "running",
        "succeeded",
        "failed",
        "disabled",
        "unconfigured",
        "idle",
    }:
        return None
    try:
        expected_version = normalize_version(payload.get("expected_version"))
    except ValueError:
        return None
    return ProjectUpdateOperation(
        operation_id=operation_id,
        expected_version=expected_version,
        requested_by=safe_requested_by(payload.get("requested_by")),
        state=state,  # type: ignore[arg-type]
        created_at=safe_timestamp(payload.get("created_at")),
        updated_at=safe_timestamp(payload.get("updated_at")),
        workflow_run_id=safe_positive_int(payload.get("workflow_run_id")),
        workflow_run_url=safe_https_url(payload.get("workflow_run_url")),
        last_polled_at=safe_timestamp(payload.get("last_polled_at")),
        message=str(payload.get("message") or "")[:500],
        error=str(payload.get("error") or "")[:1000],
    )


def operation_from_workflow_run(
    operation: ProjectUpdateOperation,
    run: dict[str, Any],
    now: float,
) -> ProjectUpdateOperation:
    """把 GitHub workflow run 状态映射为项目更新状态。"""

    status = str(run.get("status") or "").strip().lower()
    conclusion = str(run.get("conclusion") or "").strip().lower()
    run_id = safe_positive_int(run.get("id"))
    run_url = safe_https_url(run.get("html_url"))
    if status == "completed":
        if conclusion == "success":
            return replace(
                operation,
                state="succeeded",
                updated_at=now,
                last_polled_at=now,
                workflow_run_id=run_id,
                workflow_run_url=run_url,
                message="GitHub Actions 已完成部署；服务将在健康检查通过后恢复。",
                error="",
            )
        detail = conclusion or "unknown"
        return replace(
            operation,
            state="failed",
            updated_at=now,
            last_polled_at=now,
            workflow_run_id=run_id,
            workflow_run_url=run_url,
            message="GitHub Actions 部署未完成。",
            error=f"工作流结果: {detail}",
        )
    return replace(
        operation,
        state="running",
        updated_at=now,
        last_polled_at=now,
        workflow_run_id=run_id,
        workflow_run_url=run_url,
        message="GitHub Actions 正在部署发布版本。",
    )


def is_enabled(value: object) -> bool:
    """按系统配置约定读取布尔值。"""

    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off", "disabled"}


def safe_check_interval(value: object) -> int:
    """读取限制在一周内的自动检查周期。"""

    try:
        parsed = int(str(value or "24"))
    except (TypeError, ValueError):
        return 24
    return max(1, min(parsed, 168))


def safe_timestamp(value: object) -> float:
    """读取非负时间戳。"""

    try:
        return max(0.0, float(str(value or "0")))
    except (TypeError, ValueError):
        return 0.0


def safe_positive_int(value: object) -> int:
    """读取非负整数，异常数据归零。"""

    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def safe_requested_by(value: object) -> str:
    """收敛写入审计状态的操作人名称。"""

    return str(value or "superadmin").strip()[:64] or "superadmin"


def safe_https_url(value: object) -> str:
    """只保留可安全在管理端展示的 HTTPS 链接。"""

    url = str(value or "").strip()[:1000]
    return url if url.startswith("https://") else ""
