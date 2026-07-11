#!/usr/bin/env python3
"""SmartAnswer 主机更新器。

本脚本由 systemd 以 root 身份运行。业务容器只写入命令文件，GitHub、GHCR
和 Docker 凭据始终保留在宿主机。所有外部标识都经过固定来源和格式校验，
不会把命令文件内容拼接进 shell。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - systemd 生产环境为 Linux
    fcntl = None

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
OPERATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IMAGE_RE = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ACTIVE_STATES = {
    "queued",
    "checking",
    "downloading",
    "backing_up",
    "deploying",
    "verifying",
    "rolling_back",
}
MAX_JSON_BYTES = 1024 * 1024
RELEASE_MANIFEST_NAME = "release-manifest.json"


@dataclass(frozen=True, slots=True)
class UpdaterConfig:
    """主机更新器部署配置。"""

    repository: str
    image: str
    github_token: str
    ghcr_username: str
    ghcr_token: str
    project_dir: Path
    data_dir: Path
    compose_file: Path
    release_env: Path
    health_base_url: str
    min_free_bytes: int

    @classmethod
    def from_env(cls) -> "UpdaterConfig":
        """从 root-only 环境文件读取配置并校验固定来源。"""

        project_dir = Path(
            os.getenv("STQB_UPDATE_PROJECT_DIR", "/opt/study-question-bank-assistant")
        ).resolve()
        repository = os.getenv("STQB_UPDATE_REPOSITORY", "MelodyKnit/SmartAnswer").strip()
        image = os.getenv(
            "STQB_UPDATE_IMAGE", "ghcr.io/melodyknit/smartanswer"
        ).strip().lower()
        if not REPOSITORY_RE.fullmatch(repository):
            raise UpdateFailure("更新仓库配置格式不正确")
        if not IMAGE_RE.fullmatch(image):
            raise UpdateFailure("更新镜像必须位于 ghcr.io 的固定命名空间")
        return cls(
            repository=repository,
            image=image,
            github_token=os.getenv("STQB_UPDATE_GITHUB_TOKEN", "").strip(),
            ghcr_username=os.getenv("STQB_UPDATE_GHCR_USERNAME", "").strip(),
            ghcr_token=os.getenv("STQB_UPDATE_GHCR_TOKEN", "").strip(),
            project_dir=project_dir,
            data_dir=Path(
                os.getenv(
                    "STQB_UPDATE_DATA_DIR",
                    str(project_dir / "deploy-data"),
                )
            ).resolve(),
            compose_file=Path(
                os.getenv(
                    "STQB_UPDATE_COMPOSE_FILE",
                    str(project_dir / "docker-compose.yaml"),
                )
            ).resolve(),
            release_env=Path(
                os.getenv(
                    "STQB_UPDATE_RELEASE_ENV",
                    str(project_dir / ".env.release"),
                )
            ).resolve(),
            health_base_url=os.getenv(
                "STQB_UPDATE_HEALTH_BASE_URL", "http://127.0.0.1:3003"
            ).strip().rstrip("/"),
            min_free_bytes=max(
                512 * 1024 * 1024,
                int(os.getenv("STQB_UPDATE_MIN_FREE_BYTES", str(3 * 1024**3))),
            ),
        )

    @property
    def configured(self) -> bool:
        """返回私库检测与镜像拉取凭据是否齐全。"""

        return bool(self.github_token and self.ghcr_username and self.ghcr_token)

    @property
    def update_dir(self) -> Path:
        """返回应用和主机共享的更新目录。"""

        return self.data_dir / "update"


class UpdateFailure(RuntimeError):
    """可安全写入更新状态的执行错误。"""


class HostUpdater:
    """执行 GitHub Release 检测、镜像切换和自动回滚。"""

    def __init__(self, config: UpdaterConfig) -> None:
        self.config = config
        self.requests_dir = config.update_dir / "requests"
        self.operations_dir = config.update_dir / "operations"
        self.backups_dir = config.update_dir / "backups"
        self.status_path = config.update_dir / "status.json"
        self.history_path = config.update_dir / "history.json"
        self.lock_path = config.update_dir / "updater.lock"

    def initialize(self) -> None:
        """创建运行目录并发布初始配置状态。"""

        for path in (
            self.requests_dir,
            self.operations_dir,
            self.backups_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.status_path.exists():
            self.write_status(
                state="idle" if self.config.configured else "unconfigured",
                message=(
                    "主机更新器已就绪"
                    if self.config.configured
                    else "请在 /etc/stqb-updater.env 配置私有仓库凭据"
                ),
            )

    def process_queue(self) -> None:
        """依次处理业务容器写入的更新命令。"""

        self.initialize()
        with self.acquire_lock():
            for request_path in sorted(self.requests_dir.glob("*.json")):
                command: dict[str, Any] | None = None
                try:
                    command = self.read_command(request_path)
                    self.process_command(command)
                except Exception as exc:
                    operation_id = request_path.stem if OPERATION_ID_RE.fullmatch(request_path.stem) else ""
                    existing = read_json(self.operations_dir / f"{operation_id}.json")
                    terminal_state = str((existing or {}).get("state") or "")
                    if operation_id and terminal_state not in {
                        "succeeded",
                        "failed",
                        "rolled_back",
                        "rollback_failed",
                    }:
                        self.write_operation(
                            operation_id=operation_id,
                            action=str((command or {}).get("action") or "check"),
                            state="failed",
                            expected_version=str((command or {}).get("expected_version") or ""),
                            created_at=float((command or {}).get("created_at") or time.time()),
                            message="更新任务执行失败",
                            error=safe_error(exc),
                        )
                        self.write_status(
                            state="failed",
                            operation_id=operation_id,
                            action=str((command or {}).get("action") or "check"),
                            expected_version=str((command or {}).get("expected_version") or ""),
                            created_at=float((command or {}).get("created_at") or time.time()),
                            message="更新任务执行失败",
                            error=safe_error(exc),
                        )
                finally:
                    request_path.unlink(missing_ok=True)

    def scheduled_check(self) -> None:
        """执行 systemd timer 触发的周期检查。"""

        self.initialize()
        with self.acquire_lock():
            if not self.config.configured:
                self.write_status(
                    state="unconfigured",
                    message="主机更新器缺少私有仓库凭据",
                )
                return
            try:
                release, _manifest = self.fetch_latest_release()
                self.write_status(
                    state="idle",
                    latest_version=release["version"],
                    release=release,
                    checked_at=time.time(),
                    message="已完成自动版本检查",
                )
            except Exception as exc:
                self.write_status(
                    state="failed",
                    checked_at=time.time(),
                    message="自动版本检查失败",
                    error=safe_error(exc),
                    preserve_release=True,
                )

    def process_command(self, command: dict[str, Any]) -> None:
        """执行经过结构校验的单条命令。"""

        operation_id = command["operation_id"]
        action = command["action"]
        expected_version = command["expected_version"]
        created_at = command["created_at"]
        self.write_operation(
            operation_id=operation_id,
            action=action,
            state="checking",
            expected_version=expected_version,
            created_at=created_at,
            message="正在检查 GitHub Release",
        )
        self.write_status(
            state="checking",
            operation_id=operation_id,
            action=action,
            expected_version=expected_version,
            created_at=created_at,
            message="正在检查 GitHub Release",
        )
        if not self.config.configured:
            raise UpdateFailure("主机更新器缺少私有仓库凭据")

        release, manifest = self.fetch_latest_release()
        if action == "check":
            self.write_operation(
                operation_id=operation_id,
                action=action,
                state="succeeded",
                expected_version="",
                created_at=created_at,
                message="版本检查完成",
            )
            self.write_status(
                state="idle",
                latest_version=release["version"],
                operation_id=operation_id,
                action=action,
                release=release,
                checked_at=time.time(),
                message="版本检查完成",
            )
            return

        if expected_version != release["version"]:
            raise UpdateFailure("目标版本已经变化，请重新检查更新")
        self.apply_release(command, release, manifest)

    def apply_release(
        self,
        command: dict[str, Any],
        release: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        """拉取不可变镜像并在健康检查失败时自动恢复。"""

        operation_id = command["operation_id"]
        version = release["version"]
        image_ref = f"{self.config.image}@{manifest['image_digest']}"
        self.assert_deployment_paths()
        previous_env = self.config.release_env.read_text(encoding="utf-8")
        previous_values = parse_env(previous_env)
        previous_image = previous_values.get("STQB_IMAGE_REF", "")
        backup_path: Path | None = None

        self.assert_free_space()
        self.update_progress(command, "downloading", "正在拉取已签名版本镜像")
        self.pull_image(image_ref)
        self.validate_image(image_ref, manifest)
        self.preflight_image(image_ref, manifest)

        try:
            self.update_progress(command, "backing_up", "正在备份 SQLite 数据库")
            backup_path = self.backup_sqlite(operation_id)
            self.write_release_env(manifest, image_ref)
            self.update_progress(command, "deploying", "正在切换应用版本")
            self.compose_up()
            self.update_progress(command, "verifying", "正在等待新版本健康检查")
            self.wait_until_healthy(version)
        except Exception as update_error:
            self.update_progress(command, "rolling_back", "新版本验证失败，正在恢复上一版本")
            rollback_error = self.rollback(previous_env, backup_path)
            if rollback_error is not None:
                self.write_operation(
                    operation_id=operation_id,
                    action="apply",
                    state="rollback_failed",
                    expected_version=version,
                    created_at=command["created_at"],
                    message="更新失败且自动回滚失败",
                    error=f"{safe_error(update_error)}；回滚错误：{safe_error(rollback_error)}",
                )
                self.write_status(
                    state="rollback_failed",
                    operation_id=operation_id,
                    action="apply",
                    expected_version=version,
                    created_at=command["created_at"],
                    latest_version=version,
                    release=release,
                    message="更新失败且自动回滚失败",
                    error=f"{safe_error(update_error)}；回滚错误：{safe_error(rollback_error)}",
                )
                raise UpdateFailure("更新失败且自动回滚失败") from update_error
            self.write_operation(
                operation_id=operation_id,
                action="apply",
                state="rolled_back",
                expected_version=version,
                created_at=command["created_at"],
                message="新版本健康检查失败，已自动恢复上一版本",
                error=safe_error(update_error),
            )
            self.write_status(
                state="rolled_back",
                operation_id=operation_id,
                action="apply",
                expected_version=version,
                created_at=command["created_at"],
                latest_version=version,
                release=release,
                message="新版本健康检查失败，已自动恢复上一版本",
                error=safe_error(update_error),
            )
            return

        self.record_successful_image(version, image_ref, previous_image)
        self.write_operation(
            operation_id=operation_id,
            action="apply",
            state="succeeded",
            expected_version=version,
            created_at=command["created_at"],
            message=f"已更新到 {version}",
        )
        self.write_status(
            state="succeeded",
            operation_id=operation_id,
            action="apply",
            expected_version=version,
            created_at=command["created_at"],
            latest_version=version,
            release=release,
            checked_at=time.time(),
            last_success_at=time.time(),
            message=f"已更新到 {version}",
        )

    def fetch_latest_release(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """读取最新正式 Release 及其不可变镜像清单。"""

        api_url = f"https://api.github.com/repos/{self.config.repository}/releases/latest"
        release_payload = request_json(api_url, self.github_headers())
        if release_payload.get("draft") or release_payload.get("prerelease"):
            raise UpdateFailure("GitHub 返回的版本不是正式 Release")
        tag = str(release_payload.get("tag_name") or "").strip()
        version = normalize_version(tag)
        assets = release_payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateFailure("Release 缺少发布资产")
        manifest_asset = next(
            (
                item
                for item in assets
                if isinstance(item, dict) and item.get("name") == RELEASE_MANIFEST_NAME
            ),
            None,
        )
        if not manifest_asset:
            raise UpdateFailure("Release 缺少 release-manifest.json")
        asset_url = str(manifest_asset.get("url") or "")
        if not asset_url.startswith(
            f"https://api.github.com/repos/{self.config.repository}/releases/assets/"
        ):
            raise UpdateFailure("Release 清单下载地址不可信")
        manifest = request_json(
            asset_url,
            {**self.github_headers(), "Accept": "application/octet-stream"},
            max_bytes=MAX_JSON_BYTES,
        )
        validate_manifest(
            manifest,
            expected_repository=self.config.repository,
            expected_image=self.config.image,
            expected_version=version,
        )
        release = {
            "version": version,
            "name": safe_text(release_payload.get("name"), 200) or f"v{version}",
            "body": safe_text(release_payload.get("body"), 12000),
            "published_at": safe_text(release_payload.get("published_at"), 80),
            "html_url": safe_github_url(release_payload.get("html_url")),
        }
        return release, manifest

    def github_headers(self) -> dict[str, str]:
        """构造 GitHub API 请求头，不向状态或日志暴露令牌。"""

        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.config.github_token}",
            "User-Agent": "SmartAnswer-Host-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def pull_image(self, image_ref: str) -> None:
        """使用临时 Docker 凭据目录拉取私有 GHCR 镜像。"""

        with tempfile.TemporaryDirectory(prefix="stqb-docker-config-") as directory:
            env = {**os.environ, "DOCKER_CONFIG": directory}
            run_command(
                [
                    "docker",
                    "login",
                    "ghcr.io",
                    "-u",
                    self.config.ghcr_username,
                    "--password-stdin",
                ],
                env=env,
                input_text=self.config.ghcr_token,
                timeout=60,
            )
            run_command(["docker", "pull", image_ref], env=env, timeout=900)

    def validate_image(self, image_ref: str, manifest: dict[str, Any]) -> None:
        """校验镜像标签与 Release 清单一致。"""

        output = run_command(
            ["docker", "image", "inspect", image_ref, "--format", "{{json .Config.Labels}}"],
            timeout=30,
        )
        try:
            labels = json.loads(output)
        except json.JSONDecodeError as exc:
            raise UpdateFailure("无法读取候选镜像元数据") from exc
        if not isinstance(labels, dict):
            raise UpdateFailure("候选镜像缺少 OCI 元数据")
        expected = {
            "org.opencontainers.image.version": manifest["version"],
            "org.opencontainers.image.revision": manifest["commit_sha"],
            "org.opencontainers.image.source": (
                f"https://github.com/{self.config.repository}"
            ),
        }
        for key, value in expected.items():
            if labels.get(key) != value:
                raise UpdateFailure(f"候选镜像标签校验失败：{key}")

    def preflight_image(self, image_ref: str, manifest: dict[str, Any]) -> None:
        """在切换服务前验证镜像可导入并携带预期版本。"""

        output = run_command(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image_ref,
                "-c",
                (
                    "from study_qb_assistant.version import BUILD_INFO;"
                    "print(BUILD_INFO.version + ':' + BUILD_INFO.build_sha)"
                ),
            ],
            timeout=120,
        ).strip()
        expected = f"{manifest['version']}:{manifest['commit_sha']}"
        if output != expected:
            raise UpdateFailure("候选镜像预检版本不一致")

    def backup_sqlite(self, operation_id: str) -> Path | None:
        """使用 SQLite 在线备份 API 创建一致性快照。"""

        database_path = self.config.data_dir / "runtime" / "study-qb.sqlite3"
        if not database_path.exists():
            return None
        backup_dir = self.backups_dir / operation_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / "study-qb.sqlite3"
        with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as target:
            source.backup(target)
        return backup_path

    def write_release_env(self, manifest: dict[str, Any], image_ref: str) -> None:
        """原子写入 Compose 使用的不可变镜像引用。"""

        content = "\n".join(
            [
                f"STQB_IMAGE_REF={image_ref}",
                f"STQB_RELEASE_VERSION={manifest['version']}",
                f"STQB_RELEASE_SHA={manifest['commit_sha']}",
                "STQB_UPDATE_ENABLED=true",
                "",
            ]
        )
        write_text_atomic(self.config.release_env, content, mode=0o600)

    def compose_up(self) -> None:
        """使用固定 Compose 文件应用已拉取镜像。"""

        self.assert_deployment_paths()
        run_command(
            [
                "docker",
                "compose",
                "--env-file",
                str(self.config.release_env),
                "-f",
                str(self.config.compose_file),
                "up",
                "-d",
                "--no-build",
                "study-qb-assistant",
            ],
            cwd=self.config.project_dir,
            timeout=300,
        )

    def wait_until_healthy(self, expected_version: str, timeout: int = 150) -> None:
        """等待健康端点和版本端点同时满足要求。"""

        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                health = request_json(f"{self.config.health_base_url}/healthz", {})
                version = request_json(f"{self.config.health_base_url}/version", {})
                if health.get("ok") is True and version.get("version") == expected_version:
                    return
                last_error = "健康端点返回的版本不一致"
            except Exception as exc:
                last_error = safe_error(exc)
            time.sleep(2)
        raise UpdateFailure(f"新版本健康检查超时：{last_error}")

    def rollback(self, previous_env: str, backup_path: Path | None) -> Exception | None:
        """恢复上一镜像引用和更新前数据库快照。"""

        try:
            write_text_atomic(self.config.release_env, previous_env, mode=0o600)
            if backup_path is not None and backup_path.exists():
                run_command(
                    [
                        "docker",
                        "compose",
                        "--env-file",
                        str(self.config.release_env),
                        "-f",
                        str(self.config.compose_file),
                        "stop",
                        "study-qb-assistant",
                    ],
                    cwd=self.config.project_dir,
                    timeout=120,
                )
                database_path = self.config.data_dir / "runtime" / "study-qb.sqlite3"
                database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
                database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)
                shutil.copy2(backup_path, database_path)
            self.compose_up()
            previous_version = parse_env(previous_env).get("STQB_RELEASE_VERSION", "")
            if previous_version:
                self.wait_until_healthy(previous_version)
            return None
        except Exception as exc:
            return exc

    def update_progress(self, command: dict[str, Any], state: str, message: str) -> None:
        """同时更新任务与全局进度。"""

        self.write_operation(
            operation_id=command["operation_id"],
            action=command["action"],
            state=state,
            expected_version=command["expected_version"],
            created_at=command["created_at"],
            message=message,
        )
        self.write_status(
            state=state,
            operation_id=command["operation_id"],
            action=command["action"],
            expected_version=command["expected_version"],
            created_at=command["created_at"],
            message=message,
        )

    def write_operation(
        self,
        *,
        operation_id: str,
        action: str,
        state: str,
        expected_version: str,
        created_at: float,
        message: str,
        error: str = "",
    ) -> None:
        """写入前端轮询的单任务状态。"""

        write_json_atomic(
            self.operations_dir / f"{operation_id}.json",
            {
                "schema_version": 1,
                "operation_id": operation_id,
                "action": action,
                "state": state,
                "expected_version": expected_version,
                "created_at": created_at,
                "updated_at": time.time(),
                "message": message,
                "error": error,
            },
        )

    def write_status(
        self,
        *,
        state: str,
        operation_id: str = "",
        action: str = "",
        expected_version: str = "",
        latest_version: str = "",
        release: dict[str, Any] | None = None,
        checked_at: float = 0.0,
        last_success_at: float = 0.0,
        created_at: float = 0.0,
        message: str = "",
        error: str = "",
        preserve_release: bool = False,
    ) -> None:
        """原子更新供业务容器读取的全局状态。"""

        previous = read_json(self.status_path) or {}
        payload = {
            "schema_version": 1,
            "configured": self.config.configured,
            "state": state,
            "operation_id": operation_id,
            "action": action,
            "expected_version": expected_version,
            "latest_version": latest_version or previous.get("latest_version", ""),
            "release": (
                previous.get("release") if preserve_release else release or previous.get("release")
            ),
            "checked_at": checked_at or previous.get("checked_at", 0.0),
            "last_success_at": last_success_at or previous.get("last_success_at", 0.0),
            "created_at": created_at,
            "updated_at": time.time(),
            "message": message,
            "error": error,
        }
        write_json_atomic(self.status_path, payload)

    def read_command(self, path: Path) -> dict[str, Any]:
        """读取并严格校验应用提交的命令文件。"""

        payload = read_json(path)
        if not payload or payload.get("schema_version") != 1:
            raise UpdateFailure("更新命令格式不正确")
        operation_id = str(payload.get("operation_id") or "").strip().lower()
        if not OPERATION_ID_RE.fullmatch(operation_id) or path.stem != operation_id:
            raise UpdateFailure("更新任务 ID 不正确")
        action = str(payload.get("action") or "").strip().lower()
        if action not in {"check", "apply"}:
            raise UpdateFailure("更新动作不受支持")
        expected_version = str(payload.get("expected_version") or "").strip()
        if action == "apply":
            expected_version = normalize_version(expected_version)
        elif expected_version:
            raise UpdateFailure("版本检查命令不应携带目标版本")
        return {
            "operation_id": operation_id,
            "action": action,
            "expected_version": expected_version,
            "requested_by": safe_text(payload.get("requested_by"), 100),
            "created_at": max(0.0, float(payload.get("created_at") or 0.0)),
        }

    def assert_free_space(self) -> None:
        """在拉取大镜像前检查部署磁盘剩余空间。"""

        free_bytes = shutil.disk_usage(self.config.project_dir).free
        if free_bytes < self.config.min_free_bytes:
            raise UpdateFailure(
                f"磁盘空间不足，至少需要 {self.config.min_free_bytes // 1024**3}GB 可用空间"
            )

    def assert_deployment_paths(self) -> None:
        """确保 Compose 与版本环境文件位于固定项目目录内。"""

        for path in (self.config.compose_file, self.config.release_env):
            try:
                path.resolve().relative_to(self.config.project_dir)
            except ValueError as exc:
                raise UpdateFailure("部署文件必须位于项目目录内") from exc
        if not self.config.compose_file.is_file() or not self.config.release_env.is_file():
            raise UpdateFailure("Compose 或 .env.release 不存在")

    def record_successful_image(
        self,
        version: str,
        image_ref: str,
        previous_image: str,
    ) -> None:
        """保留当前和上一镜像，并仅清理更旧的本项目镜像引用。"""

        history_payload = read_json(self.history_path) or {}
        raw_items = history_payload.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        for ref in (previous_image, image_ref):
            if ref and not any(isinstance(item, dict) and item.get("image_ref") == ref for item in items):
                items.append(
                    {
                        "version": version if ref == image_ref else "previous",
                        "image_ref": ref,
                        "recorded_at": time.time(),
                    }
                )
        items = [item for item in items if isinstance(item, dict) and item.get("image_ref")]
        items.sort(key=lambda item: float(item.get("recorded_at") or 0.0), reverse=True)
        keep, remove = items[:2], items[2:]
        write_json_atomic(self.history_path, {"schema_version": 1, "items": keep})
        for item in remove:
            ref = str(item.get("image_ref") or "")
            if ref.startswith(self.config.image + "@sha256:"):
                try:
                    run_command(["docker", "image", "rm", ref], timeout=120)
                except UpdateFailure:
                    continue

    def acquire_lock(self):
        """返回跨 systemd path/timer 任务共享的文件锁上下文。"""

        return FileLock(self.lock_path)


class FileLock:
    """Linux 文件锁上下文，避免并发执行更新。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        if fcntl is not None:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateFailure("已有更新任务正在执行") from exc
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.handle is not None:
            if fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def validate_manifest(
    manifest: dict[str, Any],
    *,
    expected_repository: str,
    expected_image: str,
    expected_version: str,
) -> None:
    """验证 GitHub Release 发布清单。"""

    if manifest.get("schema_version") != 1:
        raise UpdateFailure("发布清单版本不受支持")
    version = normalize_version(manifest.get("version"))
    if version != expected_version or manifest.get("tag") != f"v{version}":
        raise UpdateFailure("发布清单版本与 Release 不一致")
    if manifest.get("repository") != expected_repository:
        raise UpdateFailure("发布清单仓库来源不一致")
    if str(manifest.get("image") or "").lower() != expected_image:
        raise UpdateFailure("发布清单镜像来源不一致")
    commit_sha = str(manifest.get("commit_sha") or "").lower()
    image_digest = str(manifest.get("image_digest") or "").lower()
    if not SHA_RE.fullmatch(commit_sha):
        raise UpdateFailure("发布清单提交号不正确")
    if not DIGEST_RE.fullmatch(image_digest):
        raise UpdateFailure("发布清单镜像摘要不正确")
    if manifest.get("platform") != "linux/amd64":
        raise UpdateFailure("发布清单不支持当前服务器平台")
    manifest["version"] = version
    manifest["commit_sha"] = commit_sha
    manifest["image_digest"] = image_digest


def request_json(
    url: str,
    headers: dict[str, str],
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    """通过 HTTPS 获取受大小限制的 JSON。"""

    if not url.startswith("https://") and not url.startswith("http://127.0.0.1:"):
        raise UpdateFailure("更新器拒绝访问不可信地址")
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > max_bytes:
                raise UpdateFailure("远程响应超过大小限制")
            payload = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise UpdateFailure(f"GitHub API 返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateFailure("无法连接 GitHub 更新源") from exc
    if len(payload) > max_bytes:
        raise UpdateFailure("远程响应超过大小限制")
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateFailure("远程更新信息不是有效 JSON") from exc
    if not isinstance(result, dict):
        raise UpdateFailure("远程更新信息结构不正确")
    return result


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int,
) -> str:
    """以参数数组执行固定程序，不经过 shell。"""

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateFailure(f"执行 {command[0]} 失败") from exc
    if completed.returncode != 0:
        detail = safe_text(completed.stderr or completed.stdout, 1200)
        raise UpdateFailure(f"{command[0]} 返回 {completed.returncode}: {detail}")
    return completed.stdout


def normalize_version(value: object) -> str:
    """读取三段稳定语义版本号。"""

    version = str(value or "").strip().removeprefix("v")
    if not SEMVER_RE.fullmatch(version):
        raise UpdateFailure("版本号必须为 X.Y.Z 格式")
    return version


def parse_env(content: str) -> dict[str, str]:
    """解析只包含简单键值的发布状态文件。"""

    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if re.fullmatch(r"[A-Z0-9_]+", key.strip()):
            values[key.strip()] = value.strip()
    return values


def read_json(path: Path) -> dict[str, Any] | None:
    """读取受大小限制的本地 JSON。"""

    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """原子写入 JSON 状态文件。"""

    write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        mode=0o640,
    )


def write_text_atomic(path: Path, content: str, *, mode: int) -> None:
    """在同一文件系统内原子替换文本文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def safe_text(value: object, limit: int) -> str:
    """截断状态文本。"""

    return str(value or "").strip()[:limit]


def safe_error(error: Exception) -> str:
    """生成不会包含请求头或凭据的错误摘要。"""

    return safe_text(error, 1000) or error.__class__.__name__


def safe_github_url(value: object) -> str:
    """只接受当前 GitHub 仓库页面链接。"""

    url = safe_text(value, 1000)
    return url if url.startswith("https://github.com/") else ""


def main(argv: list[str]) -> int:
    """执行 systemd 调用的队列处理或周期检查入口。"""

    action = argv[1] if len(argv) > 1 else "process"
    if action not in {"process", "check", "initialize"}:
        print("usage: stqb_updater.py [process|check|initialize]", file=sys.stderr)
        return 2
    try:
        updater = HostUpdater(UpdaterConfig.from_env())
        if action == "process":
            updater.process_queue()
        elif action == "check":
            updater.scheduled_check()
        else:
            updater.initialize()
        return 0
    except Exception as exc:
        print(f"stqb updater failed: {safe_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
