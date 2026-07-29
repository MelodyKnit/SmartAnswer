"""公开 GitHub Release 状态查询的回归测试。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import RLock

import httpx
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.platform.updates.contracts import (  # noqa: E402
    ProjectUpdateError,
    ProjectUpdateRelease,
)
from study_qb_assistant.platform.updates.github import (  # noqa: E402
    GitHubProjectUpdateGateway,
    project_release_from_payload,
)
from study_qb_assistant.platform.updates.service import (  # noqa: E402
    LAST_CHECK_KEY,
    ProjectUpdateService,
)
from study_qb_assistant.questions.models import CanonicalQuestionRecord  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.version import BuildInfo  # noqa: E402


class FakeProjectUpdateGateway:
    """无需真实 GitHub 网络的公开 Release 查询替身。"""

    def __init__(self) -> None:
        self.release = ProjectUpdateRelease(
            version="0.2.1",
            tag="v0.2.1",
            name="v0.2.1",
            body="测试发布说明",
            published_at="2026-07-27T10:00:00Z",
            html_url="https://github.com/example/study-qb/releases/tag/v0.2.1",
            image="ghcr.io/example/study-qb",
            image_digest="sha256:" + "a" * 64,
            build_sha="b" * 40,
        )
        self.release_error: ProjectUpdateError | None = None
        self.repositories: list[str] = []

    def latest_release(self, repository: str) -> ProjectUpdateRelease:
        self.repositories.append(repository)
        if self.release_error is not None:
            raise self.release_error
        return self.release


class ProjectUpdateTests(unittest.TestCase):
    """验证应用只读公开 Release，不再保存或使用 GitHub 凭据。"""

    def test_system_config_has_no_project_update_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(Path(directory))
            config = client.get("/api/v1/system-config", headers=headers)
            checked = client.post("/api/v1/project-update/check", headers=headers)

        self.assertEqual(config.status_code, 200)
        self.assertFalse(
            any(key.startswith("project_update_") for key in config.json()["config"])
        )
        self.assertEqual(checked.status_code, 200)
        self.assertEqual(gateway.repositories, ["example/study-qb"])
        self.assertTrue(checked.json()["update"]["has_update"])
        self.assertEqual(checked.json()["update"]["version_relation"], "behind")
        self.assertEqual(checked.json()["update"]["state"], "idle")

    def test_checked_release_older_than_current_build_is_reported_as_ahead(self) -> None:
        """手动部署的较新版本不能被误报为“已是最新 Release”。"""

        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, _ = self.create_client(
                Path(directory), build_version="0.2.2"
            )
            checked = client.post("/api/v1/project-update/check", headers=headers)

        self.assertEqual(checked.status_code, 200)
        update = checked.json()["update"]
        self.assertFalse(update["has_update"])
        self.assertEqual(update["version_relation"], "ahead")
        self.assertIn("高于最新公开 Release", update["message"])

    def test_source_repository_is_required_for_manual_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, _ = self.create_client(Path(directory), source_repository="")
            status = client.get("/api/v1/project-update/status", headers=headers)
            checked = client.post("/api/v1/project-update/check", headers=headers)

        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["update"]["available"])
        self.assertEqual(status.json()["update"]["state"], "unavailable")
        self.assertEqual(checked.status_code, 409)
        self.assertEqual(
            checked.json()["error"]["code"], "PROJECT_UPDATE_SOURCE_UNAVAILABLE"
        )

    def test_check_failure_preserves_last_verified_release_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(Path(directory))
            first = client.post("/api/v1/project-update/check", headers=headers)
            gateway.release_error = ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_UNAVAILABLE",
                "无法连接 GitHub，请检查网络或代理配置",
                http_status=503,
            )
            failed = client.post("/api/v1/project-update/check", headers=headers)
            status = client.get("/api/v1/project-update/status", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(status.json()["update"]["latest_version"], "0.2.1")
        self.assertEqual(status.json()["update"]["state"], "failed")
        self.assertTrue(status.json()["update"]["has_update"])

    def test_oversized_cached_release_state_is_ignored(self) -> None:
        """损坏的持久化状态不能拖慢管理端状态读取。"""

        with tempfile.TemporaryDirectory() as directory:
            client, platform, headers, _ = self.create_client(Path(directory))
            platform.settings.repository.set_settings(
                "project_update_state", {LAST_CHECK_KEY: "[" * 32_001}
            )
            status = client.get("/api/v1/project-update/status", headers=headers)

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["update"]["latest_version"], "")
        self.assertEqual(status.json()["update"]["state"], "idle")

    def test_startup_removes_legacy_github_update_settings(self) -> None:
        """升级后不再把旧应用内更新配置和凭据留在数据库。"""

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "runtime" / "study-qb.sqlite3"
            original = PlatformServices(database_path)
            original.settings.repository.set_settings(
                "system_config",
                {
                    "project_update_repository": "example/study-qb",
                    "project_update_github_token": "obsolete-secret",
                },
            )
            upgraded = PlatformServices(database_path)
            remaining = upgraded.settings.repository.get_settings(
                "system_config",
                keys={"project_update_repository", "project_update_github_token"},
            )

        self.assertEqual(remaining, {})

    def test_deployment_endpoints_are_not_registered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, _ = self.create_client(Path(directory))
            apply_response = client.post(
                "/api/v1/project-update/apply",
                json={"expected_version": "0.2.1"},
                headers=headers,
            )
            token_response = client.delete("/api/v1/project-update/token", headers=headers)
            operation_response = client.get(
                "/api/v1/project-update/operations/example", headers=headers
            )

        # SPA fallback may reserve an otherwise-unregistered path for GET, which
        # makes unsupported POST requests return 405 instead of 404. Either
        # status confirms the removed deployment endpoint is not callable.
        self.assertIn(apply_response.status_code, {404, 405})
        self.assertIn(token_response.status_code, {404, 405})
        self.assertIn(operation_response.status_code, {404, 405})

    def test_public_gateway_never_sends_authorization_header(self) -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/releases/latest"):
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "tag_name": "v0.2.1",
                        "name": "v0.2.1",
                        "body": "",
                        "published_at": "2026-07-27T10:00:00Z",
                        "html_url": "https://github.com/example/study-qb/releases/tag/v0.2.1",
                        "assets": [
                            {
                                "name": "release-manifest.json",
                                "url": "https://api.github.com/repos/example/study-qb/releases/assets/1",
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "schema_version": 1,
                    "repository": "example/study-qb",
                    "version": "0.2.1",
                    "tag": "v0.2.1",
                    "image": "ghcr.io/example/study-qb",
                    "image_digest": "sha256:" + "a" * 64,
                    "commit_sha": "b" * 40,
                },
            )

        gateway = GitHubProjectUpdateGateway(
            client=httpx.Client(transport=httpx.MockTransport(handle))
        )
        release = gateway.latest_release("example/study-qb")

        self.assertEqual(release.version, "0.2.1")
        self.assertEqual(len(requests), 2)
        self.assertTrue(all("authorization" not in request.headers for request in requests))
        self.assertEqual(requests[1].headers["accept"], "application/octet-stream")

    def test_manifest_mismatch_is_rejected(self) -> None:
        release = {"name": "v0.2.1", "body": "", "published_at": "", "html_url": ""}
        manifest = {
            "schema_version": 1,
            "repository": "other/repository",
            "version": "0.2.1",
            "tag": "v0.2.1",
            "image": "ghcr.io/other/repository",
            "image_digest": "sha256:" + "a" * 64,
            "commit_sha": "b" * 40,
        }

        with self.assertRaisesRegex(ProjectUpdateError, "不一致"):
            project_release_from_payload("example/study-qb", release, manifest, "0.2.1", "v0.2.1")

    def create_client(
        self,
        directory: Path,
        *,
        source_repository: str = "example/study-qb",
        build_version: str = "0.2.0",
    ) -> tuple[TestClient, PlatformServices, dict[str, str], FakeProjectUpdateGateway]:
        database_path = directory / "runtime" / "study-qb.sqlite3"
        auth = AuthService(database_path)
        platform = PlatformServices(database_path)
        gateway = FakeProjectUpdateGateway()
        platform.updates = ProjectUpdateService(
            platform.settings.repository,
            RLock(),
            gateway=gateway,
            build_info=BuildInfo(
                version=build_version,
                build_sha="c" * 40,
                build_type="release",
                source_repository=source_repository,
            ),
            clock=time.time,
        )
        client = TestClient(
            create_app(
                sample_index(), auth_service=auth, platform_services=platform, require_auth=True
            )
        )
        client.post("/api/v1/auth/register", json={"username": "owner", "password": "password123"})
        login = client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "password123"}
        )
        return client, platform, {"Authorization": f"Bearer {login.json()['token']}"}, gateway


def sample_index() -> LocalQuestionIndex:
    """构造不依赖外部数据文件的最小题库。"""

    return LocalQuestionIndex(
        (
            CanonicalQuestionRecord(
                question_id="project-update:sample",
                title_raw="项目更新测试题",
                question_type="single",
                options_raw=("A. 正确", "B. 错误"),
                answer_raw="A",
                explanation="",
                subject="test",
                chapter=None,
                tags=("project-update",),
                source_name="test",
                source_url="",
                source_license="test-only",
                source_split="active",
                source_record_path="",
            ),
        )
    )


if __name__ == "__main__":
    unittest.main()
