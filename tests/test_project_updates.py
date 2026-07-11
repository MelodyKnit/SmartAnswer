"""私有 GitHub Release 更新边界测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.local_server import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform import PlatformService  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.updates import (  # noqa: E402
    ProjectUpdateError,
    ProjectUpdateService,
)
from study_qb_assistant.version import BuildInfo  # noqa: E402


def load_host_updater_module():
    """从部署脚本加载纯逻辑，避免把宿主机工具打进应用包。"""

    module_name = "stqb_host_updater_test"
    script_path = PROJECT_ROOT / "deploy" / "updater" / "stqb_updater.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载主机更新器")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


HOST_UPDATER = load_host_updater_module()


class ProjectUpdateServiceTests(unittest.TestCase):
    """验证业务容器只通过受约束文件队列提交更新。"""

    @staticmethod
    def write_host_status(root: Path, **overrides: object) -> None:
        """写入主机更新器状态。"""

        payload: dict[str, object] = {
            "configured": True,
            "state": "idle",
            "latest_version": "0.1.27",
            "checked_at": time.time(),
            "updated_at": time.time(),
            "release": {
                "name": "v0.1.27",
                "body": "release notes",
                "published_at": "2026-07-11T00:00:00Z",
                "html_url": "https://github.com/MelodyKnit/SmartAnswer/releases/tag/v0.1.27",
            },
        }
        payload.update(overrides)
        root.mkdir(parents=True, exist_ok=True)
        (root / "status.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_status_exposes_only_safe_host_fields(self) -> None:
        """主机状态中的未知字段和凭据不得进入 API 契约。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "update"
            self.write_host_status(root, github_token="secret-release-token")
            service = ProjectUpdateService(
                root,
                enabled=True,
                build_info=BuildInfo("0.1.26", "a" * 40, "release"),
            )

            status = service.status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["has_update"])
        self.assertNotIn("github_token", status)
        self.assertNotIn("secret-release-token", json.dumps(status))

    def test_duplicate_queued_command_reuses_existing_operation(self) -> None:
        """systemd 尚未接单时，重复点击也只能生成一个命令文件。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "update"
            self.write_host_status(root)
            service = ProjectUpdateService(
                root,
                enabled=True,
                build_info=BuildInfo("0.1.26", "b" * 40, "release"),
            )

            first = service.enqueue_check(requested_by="owner")
            second = service.enqueue_check(requested_by="owner")

            self.assertEqual(first.operation_id, second.operation_id)
            self.assertEqual(len(list((root / "requests").glob("*.json"))), 1)

    def test_apply_requires_the_latest_checked_version(self) -> None:
        """安装命令必须绑定当前最新稳定版，防止确认窗口后的版本漂移。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "update"
            self.write_host_status(root)
            service = ProjectUpdateService(
                root,
                enabled=True,
                build_info=BuildInfo("0.1.26", "c" * 40, "release"),
            )

            with self.assertRaises(ProjectUpdateError) as context:
                service.enqueue_apply(expected_version="0.1.28", requested_by="owner")

            self.assertEqual(context.exception.code, "PROJECT_UPDATE_VERSION_CHANGED")


class ProjectUpdateApiTests(unittest.TestCase):
    """验证更新接口权限、异步状态码与公开版本端点。"""

    def test_version_is_public_but_update_commands_require_superadmin(self) -> None:
        """版本可用于健康验证，更新操作只能由超级管理员提交。"""

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "study-qb.sqlite3"
            update_root = Path(directory) / "update"
            ProjectUpdateServiceTests.write_host_status(update_root)
            service = ProjectUpdateService(
                update_root,
                enabled=True,
                build_info=BuildInfo("0.1.26", "d" * 40, "release"),
            )
            client = TestClient(
                create_app(
                    LocalQuestionIndex(()),
                    auth_service=AuthService(database_path),
                    platform_service=PlatformService(database_path),
                    project_update_service=service,
                    require_auth=True,
                )
            )

            version_response = client.get("/version")
            denied_response = client.post("/project-update/check")
            client.post(
                "/auth/register",
                json={"username": "owner", "password": "password123"},
            )
            login = client.post(
                "/auth/login",
                json={"username": "owner", "password": "password123"},
            )
            headers = {"Authorization": f"Bearer {login.json()['token']}"}
            queued_response = client.post("/project-update/check", headers=headers)

        self.assertEqual(version_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 401)
        self.assertEqual(queued_response.status_code, 202)
        self.assertEqual(queued_response.json()["operation"]["state"], "queued")


class HostUpdaterTests(unittest.TestCase):
    """验证发布清单与更新失败终态。"""

    @staticmethod
    def config(root: Path):
        """构造不接触真实 Docker 和网络的主机更新器配置。"""

        project_dir = root / "project"
        data_dir = project_dir / "deploy-data"
        project_dir.mkdir(parents=True)
        data_dir.mkdir()
        (project_dir / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (project_dir / ".env.release").write_text(
            "STQB_IMAGE_REF=ghcr.io/melodyknit/smartanswer@sha256:" + "1" * 64 + "\n"
            "STQB_RELEASE_VERSION=0.1.26\n",
            encoding="utf-8",
        )
        return HOST_UPDATER.UpdaterConfig(
            repository="MelodyKnit/SmartAnswer",
            image="ghcr.io/melodyknit/smartanswer",
            github_token="release-token",
            ghcr_username="melodyknit",
            ghcr_token="package-token",
            project_dir=project_dir,
            data_dir=data_dir,
            compose_file=project_dir / "docker-compose.yaml",
            release_env=project_dir / ".env.release",
            health_base_url="http://127.0.0.1:3003",
            min_free_bytes=512 * 1024 * 1024,
        )

    def test_manifest_rejects_a_different_repository(self) -> None:
        """Release 资产不能把更新器重定向到其他仓库或镜像。"""

        manifest = {
            "schema_version": 1,
            "version": "0.1.27",
            "tag": "v0.1.27",
            "repository": "attacker/repository",
            "commit_sha": "a" * 40,
            "image": "ghcr.io/melodyknit/smartanswer",
            "image_digest": "sha256:" + "b" * 64,
            "platform": "linux/amd64",
        }

        with self.assertRaises(HOST_UPDATER.UpdateFailure):
            HOST_UPDATER.validate_manifest(
                manifest,
                expected_repository="MelodyKnit/SmartAnswer",
                expected_image="ghcr.io/melodyknit/smartanswer",
                expected_version="0.1.27",
            )

    def test_process_queue_preserves_rollback_failed_terminal_state(self) -> None:
        """回滚失败必须保留为最终状态，不能被外层处理覆盖。"""

        with tempfile.TemporaryDirectory() as directory:
            updater = HOST_UPDATER.HostUpdater(self.config(Path(directory)))
            updater.initialize()
            operation_id = "a" * 32
            command = {
                "schema_version": 1,
                "operation_id": operation_id,
                "action": "apply",
                "expected_version": "0.1.27",
                "requested_by": "owner",
                "created_at": time.time(),
            }
            HOST_UPDATER.write_json_atomic(
                updater.requests_dir / f"{operation_id}.json",
                command,
            )

            def fail_after_terminal_state(parsed_command: dict[str, object]) -> None:
                updater.write_operation(
                    operation_id=operation_id,
                    action="apply",
                    state="rollback_failed",
                    expected_version="0.1.27",
                    created_at=float(parsed_command["created_at"]),
                    message="更新失败且自动回滚失败",
                    error="health check failed",
                )
                updater.write_status(
                    state="rollback_failed",
                    operation_id=operation_id,
                    action="apply",
                    expected_version="0.1.27",
                    message="更新失败且自动回滚失败",
                    error="health check failed",
                )
                raise HOST_UPDATER.UpdateFailure("rollback failed")

            with mock.patch.object(updater, "process_command", side_effect=fail_after_terminal_state):
                updater.process_queue()

            operation = HOST_UPDATER.read_json(
                updater.operations_dir / f"{operation_id}.json"
            )
            status = HOST_UPDATER.read_json(updater.status_path)

        self.assertEqual(operation["state"], "rollback_failed")
        self.assertEqual(status["state"], "rollback_failed")


if __name__ == "__main__":
    unittest.main()
