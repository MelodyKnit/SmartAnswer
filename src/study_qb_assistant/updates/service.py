"""业务容器侧的在线更新命令网关。

该服务不访问 GitHub、不执行 shell 命令，也不持有 Docker 权限。它只通过
运行数据目录提交结构化命令，并读取主机更新器写回的状态。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from ..logger import log_event
from ..version import BuildInfo
from .models import (
    ACTIVE_STATES,
    KNOWN_STATES,
    OPERATION_ID_RE,
    UpdateCommand,
    UpdateOperation,
    compare_versions,
    normalize_version,
)

MAX_STATE_FILE_BYTES = 1024 * 1024
ACTIVE_OPERATION_MAX_AGE_SECONDS = 3600


class ProjectUpdateError(Exception):
    """在线更新应用边界错误。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ProjectUpdateService:
    """管理更新状态读取与异步命令提交。"""

    def __init__(self, root: Path, *, enabled: bool, build_info: BuildInfo) -> None:
        self.root = root
        self.enabled = enabled
        self.build_info = build_info
        self.requests_dir = root / "requests"
        self.operations_dir = root / "operations"
        self.status_path = root / "status.json"

    def status(self) -> dict[str, Any]:
        """返回当前构建和主机更新器上报的安全状态。"""

        host_status = self.read_json(self.status_path) or {}
        host_configured = bool(host_status.get("configured"))
        configured = self.enabled and host_configured
        current_version = self.build_info.version
        latest_version = safe_version(host_status.get("latest_version"))
        state = safe_state(host_status.get("state"))
        if not self.enabled:
            state = "disabled"
        elif not host_configured:
            state = "unconfigured"

        has_update = False
        if configured and current_version != "dev" and latest_version:
            try:
                has_update = compare_versions(current_version, latest_version) < 0
            except ValueError:
                has_update = False

        release = host_status.get("release")
        if not isinstance(release, dict):
            release = None
        else:
            release = {
                "name": safe_text(release.get("name"), 200),
                "body": safe_text(release.get("body"), 12000),
                "published_at": safe_text(release.get("published_at"), 80),
                "html_url": safe_https_url(release.get("html_url")),
            }

        message = safe_text(host_status.get("message"), 500)
        if not self.enabled:
            message = "当前部署未启用主机更新器。"
        elif not host_configured:
            message = "主机更新器尚未配置或尚未完成首次检查。"

        return {
            "configured": configured,
            "available": has_update,
            "current_version": current_version,
            "build_sha": self.build_info.build_sha,
            "build_type": self.build_info.build_type,
            "latest_version": latest_version or current_version,
            "has_update": has_update,
            "state": state,
            "operation_id": safe_operation_id(host_status.get("operation_id")),
            "action": safe_action(host_status.get("action")),
            "expected_version": safe_version(host_status.get("expected_version")),
            "created_at": safe_timestamp(host_status.get("created_at")),
            "checked_at": safe_timestamp(host_status.get("checked_at")),
            "updated_at": safe_timestamp(host_status.get("updated_at")),
            "last_success_at": safe_timestamp(host_status.get("last_success_at")),
            "release": release,
            "message": message,
            "error": safe_text(host_status.get("error"), 1000),
        }

    def enqueue_check(self, *, requested_by: str) -> UpdateOperation:
        """提交检查最新版本命令；已有任务运行时复用该任务。"""

        return self.enqueue_command("check", expected_version="", requested_by=requested_by)

    def enqueue_apply(
        self,
        *,
        expected_version: str,
        requested_by: str,
    ) -> UpdateOperation:
        """提交应用最新稳定版命令。"""

        try:
            version = normalize_version(expected_version)
        except ValueError as exc:
            raise ProjectUpdateError("INVALID_INPUT", str(exc), http_status=400) from exc
        status = self.status()
        if not status["has_update"] or status["latest_version"] != version:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_VERSION_CHANGED",
                "目标版本已变化，请重新检查更新后再试",
                http_status=409,
            )
        return self.enqueue_command("apply", expected_version=version, requested_by=requested_by)

    def enqueue_command(
        self,
        action: str,
        *,
        expected_version: str,
        requested_by: str,
    ) -> UpdateOperation:
        """以原子文件写入方式提交主机命令。"""

        self.assert_configured()
        existing = self.active_operation()
        if existing is not None:
            return existing
        if action not in {"check", "apply"}:
            raise ProjectUpdateError("INVALID_INPUT", "不支持的更新操作", http_status=400)

        now = time.time()
        operation_id = uuid.uuid4().hex
        command = UpdateCommand(
            operation_id=operation_id,
            action=action,
            expected_version=expected_version,
            requested_by=safe_text(requested_by, 100),
            created_at=now,
        )
        operation = UpdateOperation(
            operation_id=operation_id,
            action=action,
            state="queued",
            expected_version=expected_version,
            created_at=now,
            updated_at=now,
            message="更新任务已进入队列",
        )
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.operations_dir.mkdir(parents=True, exist_ok=True)
        operation_path = self.operations_dir / f"{operation_id}.json"
        request_path = self.requests_dir / f"{operation_id}.json"
        try:
            write_json_atomic(operation_path, operation.to_dict())
            write_json_atomic(request_path, command.to_dict())
        except OSError as exc:
            operation_path.unlink(missing_ok=True)
            raise ProjectUpdateError(
                "PROJECT_UPDATE_QUEUE_UNAVAILABLE",
                "无法写入主机更新队列，请检查部署目录权限",
                http_status=503,
            ) from exc
        log_event(
            "project_update_queued",
            {
                "operation_id": operation_id,
                "action": action,
                "expected_version": expected_version,
                "requested_by": safe_text(requested_by, 100),
            },
        )
        return operation

    def operation(self, operation_id: str) -> UpdateOperation:
        """读取指定异步操作状态。"""

        normalized = safe_operation_id(operation_id)
        if not normalized:
            raise ProjectUpdateError("INVALID_INPUT", "任务 ID 格式不正确", http_status=400)
        payload = self.read_json(self.operations_dir / f"{normalized}.json")
        if not payload:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_OPERATION_NOT_FOUND",
                "更新任务不存在",
                http_status=404,
            )
        return operation_from_payload(payload)

    def active_operation(self) -> UpdateOperation | None:
        """返回仍在运行或等待主机接收的操作。"""

        host_status = self.read_json(self.status_path) or {}
        operation_id = safe_operation_id(host_status.get("operation_id"))
        state = safe_state(host_status.get("state"))
        if operation_id and state in ACTIVE_STATES:
            try:
                return self.operation(operation_id)
            except ProjectUpdateError:
                return UpdateOperation(
                    operation_id=operation_id,
                    action=safe_action(host_status.get("action")),
                    state=state,
                    expected_version=safe_version(host_status.get("expected_version")),
                    created_at=safe_timestamp(host_status.get("created_at")),
                    updated_at=safe_timestamp(host_status.get("updated_at")),
                    message=safe_text(host_status.get("message"), 500),
                    error=safe_text(host_status.get("error"), 1000),
                )

        # 主机更新器尚未被 systemd.path 唤醒时，全局状态还没有 operation_id。
        # 扫描最近的队列状态可防止用户连续点击产生多个并发更新命令。
        try:
            operation_paths = sorted(
                self.operations_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:50]
        except OSError:
            return None
        now = time.time()
        for path in operation_paths:
            payload = self.read_json(path)
            if not payload:
                continue
            try:
                operation = operation_from_payload(payload)
            except ProjectUpdateError:
                continue
            if (
                operation.state in ACTIVE_STATES
                and now - operation.updated_at <= ACTIVE_OPERATION_MAX_AGE_SECONDS
            ):
                return operation
        return None

    def assert_configured(self) -> None:
        """确保当前部署已启用并配置主机更新器。"""

        status = self.status()
        if not status["configured"]:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_UNCONFIGURED",
                status["message"],
                http_status=503,
            )

    @staticmethod
    def read_json(path: Path) -> dict[str, Any] | None:
        """读取受大小限制的状态 JSON；损坏文件按无状态处理。"""

        try:
            if path.stat().st_size > MAX_STATE_FILE_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None


def operation_from_payload(payload: dict[str, Any]) -> UpdateOperation:
    """将主机状态文件收敛为稳定的操作契约。"""

    operation_id = safe_operation_id(payload.get("operation_id"))
    if not operation_id:
        raise ProjectUpdateError(
            "PROJECT_UPDATE_OPERATION_INVALID",
            "更新任务状态损坏",
            http_status=500,
        )
    return UpdateOperation(
        operation_id=operation_id,
        action=safe_action(payload.get("action")),
        state=safe_state(payload.get("state")),
        expected_version=safe_version(payload.get("expected_version")),
        created_at=safe_timestamp(payload.get("created_at")),
        updated_at=safe_timestamp(payload.get("updated_at")),
        message=safe_text(payload.get("message"), 500),
        error=safe_text(payload.get("error"), 1000),
    )


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """在同目录写入临时文件后原子替换目标文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def safe_text(value: object, limit: int) -> str:
    """收敛主机状态中的文本，避免异常对象和超长内容进入响应。"""

    return str(value or "").strip()[:limit]


def safe_timestamp(value: object) -> float:
    """读取非负时间戳。"""

    if not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def safe_version(value: object) -> str:
    """读取合法语义版本，异常值返回空。"""

    try:
        return normalize_version(value)
    except ValueError:
        return ""


def safe_state(value: object) -> str:
    """读取已知状态，未知值收敛为 idle。"""

    state = safe_text(value, 40).lower()
    return state if state in KNOWN_STATES else "idle"


def safe_operation_id(value: object) -> str:
    """读取合法操作 ID。"""

    operation_id = safe_text(value, 64).lower()
    return operation_id if OPERATION_ID_RE.fullmatch(operation_id) else ""


def safe_action(value: object) -> str:
    """读取更新动作。"""

    action = safe_text(value, 20).lower()
    return action if action in {"check", "apply"} else "check"


def safe_https_url(value: object) -> str:
    """只允许 GitHub 状态提供 HTTPS 链接。"""

    url = safe_text(value, 1000)
    return url if url.startswith("https://") else ""
